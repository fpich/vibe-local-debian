from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from vibe.core.config.harness_files import (
    HarnessFilesManager,
    get_harness_files_manager,
)
from vibe.core.skills.builtins import BUILTIN_SKILLS
from vibe.core.skills.models import (
    ParsedSkillCommand,
    RegistryRef,
    SkillConfigIssue,
    SkillInfo,
    SkillMetadata,
    SkillScope,
    SkillSource,
)
from vibe.core.skills.parser import (
    SkillParseError,
    load_openai_skill_metadata,
    openai_skill_metadata_path,
    parse_skill_markdown,
)
from vibe.core.utils import name_matches
from vibe.observability.logging import logger
from vibe.utils.io import read_safe

if TYPE_CHECKING:
    from vibe.core.config import VibeConfigSchema


class SkillManager:
    def __init__(
        self,
        config_getter: Callable[[], VibeConfigSchema],
        *,
        harness_files: HarnessFilesManager | None = None,
        include_builtins: bool = True,
    ) -> None:
        self._config_getter = config_getter
        self._harness_files = harness_files or get_harness_files_manager()
        self._include_builtins = include_builtins
        self._search_paths = self._compute_search_paths(self._config)
        self._config_issues: list[SkillConfigIssue] = []
        self._discovered = self._discover_skills()
        self.available_skills: Mapping[str, SkillInfo] = MappingProxyType(
            self._apply_filters(self._discovered)
        )

        if self.available_skills:
            logger.info(
                "Discovered %d skill(s) from %d search path(s)",
                len(self.available_skills),
                len(self._search_paths),
            )

    @property
    def _config(self) -> VibeConfigSchema:
        return self._config_getter()

    @property
    def config_issues(self) -> tuple[SkillConfigIssue, ...]:
        return tuple(self._config_issues)

    def _apply_filters(self, skills: dict[str, SkillInfo]) -> dict[str, SkillInfo]:
        if self._config.enabled_skills:
            return {
                name: info
                for name, info in skills.items()
                if name_matches(name, self._config.enabled_skills)
            }
        if self._config.disabled_skills:
            return {
                name: info
                for name, info in skills.items()
                if not name_matches(name, self._config.disabled_skills)
            }
        return dict(skills)

    def _compute_search_paths(
        self, config: VibeConfigSchema
    ) -> list[tuple[Path, SkillScope]]:
        paths: list[tuple[Path, SkillScope]] = []

        for path in config.skill_paths:
            if path.is_dir():
                paths.append((path, SkillScope.GLOBAL))

        mgr = self._harness_files
        paths.extend((p, SkillScope.PROJECT) for p in mgr.project_skills_dirs)
        paths.extend((p, SkillScope.GLOBAL) for p in mgr.user_skills_dirs)

        global_paths = {p.resolve() for p in mgr.user_skills_dirs}
        global_paths.update(
            p.resolve() for p, scope in paths if scope is SkillScope.GLOBAL
        )

        unique: list[tuple[Path, SkillScope]] = []
        seen: set[Path] = set()
        for p, scope in paths:
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            if scope is SkillScope.PROJECT and rp in global_paths:
                scope = SkillScope.GLOBAL
            unique.append((rp, scope))

        return unique

    def _discover_skills(self) -> dict[str, SkillInfo]:
        skills: dict[str, SkillInfo] = {**self._reserved_builtins}
        for base, scope in self._search_paths:
            if not base.is_dir():
                continue
            for name, info in self._discover_skills_in_dir(base, scope).items():
                if name not in skills:
                    skills[name] = info
                else:
                    logger.debug(
                        "Skipping duplicate skill '%s' at %s (already loaded from %s)",
                        name,
                        info.skill_path,
                        skills[name].skill_path,
                    )
        return skills

    def _discover_skills_in_dir(
        self, base: Path, scope: SkillScope
    ) -> dict[str, SkillInfo]:
        skills: dict[str, SkillInfo] = {}
        for skill_dir in base.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                continue
            skill_info = self._try_load_skill(
                skill_file, source=SkillSource.LOCAL, scope=scope
            )
            if skill_info is None:
                continue
            if skill_info.name in self._reserved_builtins:
                logger.debug(
                    "Skipping skill '%s' at %s because builtin skill names are reserved",
                    skill_info.name,
                    skill_info.skill_path,
                )
                continue
            if skill_info.name in skills:
                logger.debug(
                    "Skipping duplicate skill '%s' at %s (already loaded from %s)",
                    skill_info.name,
                    skill_info.skill_path,
                    skills[skill_info.name].skill_path,
                )
                continue
            skills[skill_info.name] = skill_info
        return skills

    def registry_pins(self) -> list[SkillInfo]:
        """Remote registry skills are not available in local-only builds."""
        return []

    def installed_skills(self) -> list[SkillInfo]:
        """Everything installed, one entry per (name, scope, source).

        Not de-duped: a skill pinned both globally and in the project is two
        pins the user can manage separately, and a registry pin shadowed by a
        local file of the same name is still a manifest entry they can remove.
        Collapsing by name here is what made those unreachable. The browser
        collapses for display and keeps this set for per-scope actions.

        Builtins are excluded, and skills matched by ``disabled_skills`` are
        kept so one turned off can be turned back on.

        Reads the discovery done at construction rather than re-walking the
        search paths, so listing does not hit the disk on the event loop.
        """
        out: dict[tuple[str, SkillScope, SkillSource], SkillInfo] = {}
        for info in self._discovered.values():
            if info.source is SkillSource.LOCAL:
                out[(info.name, info.scope, info.source)] = info
        for base, scope in self._search_paths:
            if not base.is_dir():
                continue
            for name, info in self._discover_skills_in_dir(base, scope).items():
                out.setdefault((name, scope, SkillSource.LOCAL), info)
        return list(out.values())

    def _try_load_skill(
        self,
        skill_file: Path,
        *,
        source: SkillSource,
        scope: SkillScope,
        registry: RegistryRef | None = None,
        check_dir_name: bool = True,
    ) -> SkillInfo | None:
        try:
            skill_info = self._parse_skill_file(
                skill_file,
                source=source,
                scope=scope,
                registry=registry,
                check_dir_name=check_dir_name,
            )
        except Exception as e:
            logger.warning("Failed to parse skill at %s: %s", skill_file, e)
            self._config_issues.append(
                SkillConfigIssue(file=skill_file, message=f"Failed to load: {e}")
            )
            return None
        return skill_info

    def _parse_skill_file(
        self,
        skill_path: Path,
        *,
        source: SkillSource,
        scope: SkillScope,
        registry: RegistryRef | None = None,
        check_dir_name: bool = True,
    ) -> SkillInfo:
        try:
            content = read_safe(skill_path).text
        except OSError as e:
            raise SkillParseError(f"Cannot read file: {e}") from e

        frontmatter, body = parse_skill_markdown(content)
        metadata = SkillMetadata.model_validate(frontmatter)

        if check_dir_name:
            skill_name_from_dir = skill_path.parent.name
            if metadata.name != skill_name_from_dir:
                logger.warning(
                    "Skill name '%s' doesn't match directory name '%s' at %s",
                    metadata.name,
                    skill_name_from_dir,
                    skill_path,
                )

        return SkillInfo.from_metadata(
            metadata,
            skill_path,
            prompt=body.strip(),
            source=source,
            scope=scope,
            registry=registry,
            model_invocable=self._openai_allows_implicit_invocation(skill_path),
        )

    def _openai_allows_implicit_invocation(self, skill_path: Path) -> bool:
        metadata_path = openai_skill_metadata_path(skill_path)
        try:
            metadata = load_openai_skill_metadata(skill_path)
        except SkillParseError as e:
            logger.warning("Failed to parse skill metadata at %s: %s", metadata_path, e)
            self._config_issues.append(
                SkillConfigIssue(
                    file=metadata_path, message=f"Model invocation disabled: {e}"
                )
            )
            return False
        return metadata is None or metadata.allows_implicit_invocation

    @property
    def _reserved_builtins(self) -> Mapping[str, SkillInfo]:
        # The names are reserved because the builtins occupy them. A caller that
        # sources them elsewhere occupies nothing, so nothing is held back.
        return BUILTIN_SKILLS if self._include_builtins else {}

    @property
    def custom_skills_count(self) -> int:
        return sum(
            name not in self._reserved_builtins for name in self.available_skills
        )

    def get_skill(self, name: str) -> SkillInfo | None:
        return self.available_skills.get(name)

    def get_model_invocable_skill(self, name: str) -> SkillInfo | None:
        skill = self.get_skill(name)
        if skill is None or not skill.model_invocable:
            return None
        return skill

    def parse_skill_command(self, text_prompt: str) -> ParsedSkillCommand | None:
        stripped = text_prompt.strip()
        if not stripped.startswith("/"):
            return None

        parts = stripped[1:].split(None, 1)
        if not parts:
            return None

        skill_name = parts[0].lower()
        skill_info = self.get_skill(skill_name)
        if skill_info is None or not skill_info.user_invocable:
            return None

        extra_instructions = parts[1] if len(parts) > 1 else None

        return ParsedSkillCommand(
            name=skill_name,
            content=skill_info.prompt,
            extra_instructions=extra_instructions,
        )
