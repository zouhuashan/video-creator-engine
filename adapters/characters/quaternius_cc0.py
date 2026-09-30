"""Project-local installation for the Quaternius CC0 humanoid base pack.
The downloaded archive is treated as an inbound dependency.  A production
project receives its own immutable copy of the two glTF characters plus their
textures and license, so rendering never depends on a temporary browser path.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


class QuaterniusAssetError(RuntimeError):
    pass


class QuaterniusCC0Characters:
    id = "quaternius_universal_base_characters_standard"
    version = "2025-12-16"
    license = "CC0-1.0"
    source_page = "https://quaternius.com/packs/universalbasecharacters.html"
    download_page = "https://quaternius.itch.io/universal-base-characters"
    archive_sha256 = "fdbf1804c90dfc1ea03e992bff7da2dfd1a79318e13270a660180f9308455f40"

    def __init__(self, repository: Path):
        self.repository = Path(repository).resolve()
        self.dependency = self.repository / ".dependencies/free-assets/quaternius"
        self.archive = self.dependency / "Universal Base Characters[Standard].zip"
        self.source = self.dependency / "extracted/Universal Base Characters[Standard]"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _validate_source(self) -> None:
        if not self.archive.is_file() or self._sha256(self.archive) != self.archive_sha256:
            raise QuaterniusAssetError("Quaternius Standard 免费资源包缺失或哈希不匹配")
        required = (
            self.source / "License_Standard.txt",
            self.source / "Base Characters/Godot - UE/Superhero_Male_FullBody.gltf",
            self.source / "Base Characters/Godot - UE/Superhero_Male_FullBody.bin",
            self.source / "Base Characters/Godot - UE/Superhero_Female_FullBody.gltf",
            self.source / "Base Characters/Godot - UE/Superhero_Female_FullBody.bin",
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise QuaterniusAssetError("Quaternius Standard 解压内容不完整：" + ", ".join(missing))

    def install(self, project: Path) -> dict[str, object]:
        self._validate_source()
        project = Path(project).resolve()
        target = project / "production/assets/characters/quaternius-cc0"
        model_target = target / "models"
        hair_target = target / "hair"
        model_target.mkdir(parents=True, exist_ok=True)
        hair_target.mkdir(parents=True, exist_ok=True)

        model_source = self.source / "Base Characters/Godot - UE"
        for path in model_source.iterdir():
            if path.is_file():
                shutil.copy2(path, model_target / path.name)

        # Two upstream glTF texture names use a `_png` suffix although the
        # archive contains the same PNG without it. Keep both names locally.
        aliases = {
            "T_Hair_1_Normal_png.png": "T_Hair_1_Normal.png",
            "T_Eye_Normal_png.png": "T_Eye_Normal.png",
        }
        for alias, original in aliases.items():
            shutil.copy2(model_target / original, model_target / alias)

        hair_source = self.source / "Hairstyles/Origin at 0/glTF (Godot)"
        for stem in ("Hair_SimpleParted", "Hair_Buns"):
            for suffix in (".gltf", ".bin"):
                shutil.copy2(hair_source / f"{stem}{suffix}", hair_target / f"{stem}{suffix}")
        for path in hair_source.glob("T_Hair_*.png"):
            shutil.copy2(path, hair_target / path.name)
        shutil.copy2(self.source / "License_Standard.txt", target / "LICENSE.txt")

        expected_bones = {
            "root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "Head",
            "upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r",
            "thumb_01_l", "index_01_l", "middle_01_l", "thumb_01_r", "index_01_r", "middle_01_r",
        }
        files: dict[str, dict[str, object]] = {}
        for path in sorted(item for item in target.rglob("*") if item.is_file()):
            relative = path.relative_to(project).as_posix()
            files[relative] = {"sha256": self._sha256(path), "bytes": path.stat().st_size}

        roles = {
            "陈浩": "models/Superhero_Male_FullBody.gltf",
            "林晓": "models/Superhero_Female_FullBody.gltf",
            "主管": "models/Superhero_Male_FullBody.gltf",
        }
        inspected: dict[str, object] = {}
        for role, relative in roles.items():
            data = json.loads((target / relative).read_text(encoding="utf-8"))
            bones = {node.get("name") for node in data.get("nodes", [])}
            missing = sorted(expected_bones - bones)
            if missing:
                raise QuaterniusAssetError(f"{role} 基模缺少骨骼：{', '.join(missing)}")
            inspected[role] = {
                "asset": (target / relative).relative_to(project).as_posix(),
                "skeleton_bones": len(data.get("skins", [{}])[0].get("joints", [])),
                "animations": len(data.get("animations", [])),
                "hair": "hair/Hair_Buns.gltf" if role == "林晓" else "hair/Hair_SimpleParted.gltf",
            }

        manifest = {
            "schema_version": 1,
            "adapter": self.id,
            "version": self.version,
            "source_page": self.source_page,
            "download_page": self.download_page,
            "archive_sha256": self.archive_sha256,
            "license": self.license,
            "license_file": (target / "LICENSE.txt").relative_to(project).as_posix(),
            "roles": inspected,
            "files": files,
            "capabilities": {
                "fixed_identity": True,
                "humanoid_rig": True,
                "finger_bones": True,
                "facial_blendshapes": False,
                "body_animation_embedded": False,
            },
            "review_status": "PENDING",
            "use_limit": "角色表演样段；正式造型、服装与面部精度仍需人工验收",
        }
        manifest_path = target / "asset-manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest
