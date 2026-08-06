#!/usr/bin/env python3
"""SkillSafe deterministisch als portables .skill-ZIP paketieren."""

import argparse
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_SKILL = REPOSITORY / "wissenstresor"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

# Erlaubte Dateiarten im Paket. Spiegelbild von ARTEFAKT_SUFFIXE,
# ARTEFAKT_DATEINAMEN und ENGINE_SCRIPT in wissenstresor/scripts/vault.py,
# bewusst doppelt geführt: der Paketbau darf nicht von dem Script abhängen,
# das er gerade verpackt. Zwei unabhängige Gates statt eines geteilten.
# .svg bleibt draußen (aktive Inhalte), .py nur als das eine Engine-Script.
ALLOWED_SUFFIXES = frozenset({
    ".md", ".json", ".yaml", ".sha256",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".pdf",
})
ALLOWED_EXTENSIONLESS = frozenset({"LICENSE", "VERSION"})
ENGINE_SCRIPT = "scripts/vault.py"
# Host-lokale Dateien: nie im Paket, nie im Manifest. .vault-extern.json
# enthaelt absolute Pfade DIESER Maschine — waere sie im Archiv, haenge die
# reproduzierbare Paket-SHA-256 am Rechner statt am Bestand. Dass vault.py
# sie ebenfalls ausschliesst, reicht hier bewusst nicht: zwei unabhaengige
# Gates, wie bei der Dateiart-Allowlist.
HOST_LOCAL_FILES = frozenset({".vault-release.lock", ".vault-extern.json"})


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(path, root):
    relative = path.relative_to(root).as_posix()
    pure = PurePosixPath(relative)
    if (
        not relative
        or pure.is_absolute()
        or ".." in pure.parts
        or "\\" in relative
        or any(ord(char) < 32 or ord(char) == 127 for char in relative)
    ):
        raise ValueError(f"nicht portabler Paketpfad: {relative!r}")
    return relative


def collect_files(skill):
    files = []
    seen_inodes = set()
    for current, directories, names in os.walk(skill, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_directories = []
        for name in sorted(directories):
            path = current_path / name
            if name.startswith("."):
                raise ValueError(f"versteckter Ordner darf nicht ins Paket: {path}")
            status = os.lstat(path)
            if stat.S_ISLNK(status.st_mode):
                raise ValueError(f"Symlink-Verzeichnis verboten: {path}")
            if not stat.S_ISDIR(status.st_mode):
                raise ValueError(f"kein echtes Verzeichnis: {path}")
            relative = safe_relative(path, skill)
            if relative == "evals" or "__pycache__" in PurePosixPath(relative).parts:
                continue
            kept_directories.append(name)
        directories[:] = kept_directories
        for name in sorted(names):
            path = current_path / name
            relative = safe_relative(path, skill)
            pure = PurePosixPath(relative)
            if name.startswith(".") and name not in HOST_LOCAL_FILES:
                raise ValueError(
                    f"versteckte Datei darf nicht ins Paket: {relative}"
                )
            if (
                name in HOST_LOCAL_FILES
                or path.suffix == ".pyc"
                or "__pycache__" in pure.parts
                or pure.parts[:1] == ("evals",)
            ):
                continue
            if (
                pure.parts[:2] == ("sources", "quarantine")
                and relative != "sources/quarantine/README.md"
            ):
                raise ValueError(f"Quarantäne-Payload darf nicht ins Paket: {relative}")
            status = os.lstat(path)
            if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
                raise ValueError(f"nur reguläre Dateien erlaubt: {relative}")
            if status.st_nlink != 1:
                raise ValueError(f"Hardlink verboten: {relative}")
            inode = (status.st_dev, status.st_ino)
            if inode in seen_inodes:
                raise ValueError(f"mehrfach verlinkte Datei: {relative}")
            seen_inodes.add(inode)
            suffix = path.suffix.lower()
            if relative != ENGINE_SCRIPT:
                if suffix and suffix not in ALLOWED_SUFFIXES:
                    raise ValueError(
                        f"Dateiart {suffix} gehört nicht ins Paket: {relative}"
                    )
                if not suffix and name not in ALLOWED_EXTENSIONLESS:
                    raise ValueError(
                        f"Datei ohne Endung gehört nicht ins Paket: {relative}"
                    )
            if status.st_mode & 0o111:
                raise ValueError(
                    f"ausführbare Datei gehört nicht ins Paket: {relative}"
                )
            files.append((relative, path))
    files.sort(key=lambda item: item[0])
    if not files or files[0][0] == "":
        raise ValueError("keine Skill-Dateien gefunden")
    return files


def validate_skill_contract(skill):
    skill_file = skill / "SKILL.md"
    if not skill_file.is_file() or skill_file.is_symlink():
        raise ValueError("SKILL.md fehlt oder ist kein echtes Dokument")
    text = skill_file.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > 128 * 1024:
        raise ValueError("SKILL.md überschreitet die portable 128-KiB-Grenze")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md beginnt nicht mit Frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("SKILL.md-Frontmatter ist nicht geschlossen") from exc
    fields = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or key.strip() in fields:
            raise ValueError(f"ungültige Frontmatter-Zeile: {line!r}")
        fields[key.strip()] = value.strip()
    if set(fields) != {"name", "description"}:
        raise ValueError("SKILL.md-Frontmatter braucht exakt name + description")
    name = fields["name"].strip("\"'")
    description = fields["description"].strip("\"'")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError(f"nicht portabler Skill-Name: {name!r}")
    if len(name) > 64:
        raise ValueError("Skill-Name darf höchstens 64 Zeichen lang sein")
    if not 1 <= len(description) <= 1024:
        raise ValueError("Skill-Beschreibung muss 1 bis 1024 Zeichen lang sein")
    return name


def write_archive(target, root_name, files):
    with zipfile.ZipFile(target, "w", allowZip64=True) as archive:
        for relative, source in files:
            archive_name = f"{root_name}/{relative}"
            info = zipfile.ZipInfo(archive_name, FIXED_ZIP_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.flag_bits |= 0x800
            info.file_size = source.stat().st_size
            with archive.open(
                info, "w", force_zip64=info.file_size >= zipfile.ZIP64_LIMIT
            ) as destination:
                with open(source, "rb") as stream:
                    shutil.copyfileobj(stream, destination, length=1024 * 1024)


def verify_archive(archive_path, root_name, files):
    expected = {
        f"{root_name}/{relative}": source for relative, source in files
    }
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        if archive.testzip() is not None:
            raise ValueError("ZIP-Integritätsprüfung fehlgeschlagen")
        if len(names) != len(set(names)):
            raise ValueError("doppelte ZIP-Einträge")
        prefix = root_name + "/"
        for name in names:
            pure = PurePosixPath(name)
            if (
                not name.startswith(prefix)
                or pure.is_absolute()
                or ".." in pure.parts
                or "\\" in name
            ):
                raise ValueError(f"unsicherer ZIP-Eintrag: {name!r}")
        if set(names) != set(expected):
            raise ValueError("ZIP-Dateiliste weicht vom freigegebenen Skill ab")
        for name in sorted(names):
            digest = hashlib.sha256()
            with archive.open(name, "r") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != sha256(expected[name]):
                raise ValueError(f"ZIP-Inhalt weicht von Quelle ab: {name}")


def run_doctor(skill, cwd):
    result = subprocess.run(
        [sys.executable, "-B", str(skill / "scripts/vault.py"), "doctor"],
        cwd=cwd,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"doctor fehlgeschlagen:\n{result.stdout}{result.stderr}"
        )


def build(skill, output, force=False):
    skill = skill.resolve(strict=True)
    output = Path(os.path.abspath(output))
    if not skill.is_dir():
        raise ValueError(f"Skill-Ordner fehlt: {skill}")
    try:
        output.resolve(strict=False).relative_to(skill)
    except ValueError:
        pass
    else:
        raise ValueError("Paket-Ausgabe darf nicht innerhalb des Skill-Ordners liegen")
    root_name = skill.name
    skill_name = validate_skill_contract(skill)
    if root_name != skill_name:
        raise ValueError(
            f"Skill-Ordner {root_name!r} muss Frontmatter-name "
            f"{skill_name!r} entsprechen"
        )
    run_doctor(skill, skill)
    files = collect_files(skill)
    with tempfile.TemporaryDirectory(prefix="skillsafe-package-") as temporary:
        temporary_root = Path(temporary)
        first = temporary_root / "first.skill"
        second = temporary_root / "second.skill"
        write_archive(first, root_name, files)
        write_archive(second, root_name, files)
        verify_archive(first, root_name, files)
        verify_archive(second, root_name, files)
        if sha256(first) != sha256(second) or first.stat().st_size != second.stat().st_size:
            raise RuntimeError("zwei Paket-Builds sind nicht byteidentisch")

        extracted = temporary_root / "claude-install" / ".claude" / "skills"
        project = temporary_root / "foreign-project"
        extracted.mkdir(parents=True)
        project.mkdir()
        with zipfile.ZipFile(first, "r") as archive:
            archive.extractall(extracted)
        run_doctor(extracted / root_name, project)

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            if output.is_symlink() or not output.is_file():
                raise ValueError(f"unsicheres bestehendes Ausgabeziel: {output}")
            if output.stat().st_size == first.stat().st_size and sha256(output) == sha256(first):
                return output, sha256(output), len(files), "unchanged"
            if not force:
                raise FileExistsError(
                    f"{output} existiert mit anderem Inhalt; --force zum Ersetzen"
                )
        stage_fd, staged_name = tempfile.mkstemp(
            prefix=f".{output.name}.tmp-", dir=output.parent
        )
        staged = Path(staged_name)
        try:
            with os.fdopen(stage_fd, "wb") as destination:
                with open(first, "rb") as source:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
                os.fchmod(destination.fileno(), 0o644)
            os.replace(staged, output)
        finally:
            if staged.exists():
                staged.unlink()
    return output, sha256(output), len(files), "written"


def main():
    parser = argparse.ArgumentParser(
        description="SkillSafe lokal und deterministisch als .skill paketieren"
    )
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    version_file = args.skill / "VERSION"
    if not version_file.is_file():
        parser.error(f"VERSION fehlt unter {args.skill}")
    version = version_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        parser.error(f"VERSION ist kein SemVer x.y.z: {version!r}")
    output = args.output or (
        REPOSITORY / "dist" / f"wissenstresor-{version}.skill"
    )
    try:
        path, digest, count, state = build(args.skill, output, force=args.force)
    except (FileExistsError, OSError, RuntimeError, ValueError) as exc:
        print(f"package: FEHLER — {exc}", file=sys.stderr)
        return 1
    print(f"package: {state} — {path}")
    print(f"sha256: {digest}")
    print(f"files: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
