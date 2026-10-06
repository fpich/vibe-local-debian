from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from pydantic import ValidationError
from rich import print as rprint
from rich.markup import escape

from vibe import __version__
from vibe.cli.session_exit import print_session_resume_message
from vibe.cli.terminal_detect import detect_terminal
from vibe.core.config import VibeConfigSchema, load_dotenv_values
from vibe.core.config.default_orchestrator import build_default_orchestrator
from vibe.core.config.layer import ConfigStorageError
from vibe.core.config.orchestrator import ConfigOrchestrator
from vibe.core.paths import HISTORY_FILE, bootstrap_vibe_home

# The TUI and programmatic runner are imported at their call sites so startup
# only loads the surface the user selected.

if TYPE_CHECKING:
    from vibe.app_server.local import LocalSessionIntent


def get_prompt_from_stdin() -> str | None:
    if sys.stdin.isatty():
        return None
    try:
        content = sys.stdin.read().strip()
    except KeyboardInterrupt:
        return None
    if content:
        try:
            sys.stdin = sys.__stdin__ = open("/dev/tty")
        except OSError:
            pass
        return content
    return None


def _format_config_validation_error(exc: ValidationError) -> str:
    lines = [f"Invalid configuration ({exc.error_count()} error(s)):"]
    for err in exc.errors(include_url=False):
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def load_config_orchestrator_or_exit() -> ConfigOrchestrator[VibeConfigSchema]:
    try:
        return asyncio.run(build_default_orchestrator())
    except ValidationError as e:
        rprint(f"[yellow]{_format_config_validation_error(e)}[/]")
        sys.exit(1)
    except ConfigStorageError as e:
        rprint(
            f"[yellow]Cannot {e.operation} the Vibe config file at {e.path}: "
            f"{e.__cause__}.\nVibe needs read/write access to it. If it is managed "
            "read-only (e.g. symlinked from the Nix store), make it writable or set "
            "VIBE_HOME to a writable directory.[/]"
        )
        sys.exit(1)
    except ValueError as e:
        rprint(f"[yellow]{escape(str(e))}[/]")
        sys.exit(1)


def _agent_selection(args: argparse.Namespace) -> tuple[str | None, bool]:
    from vibe.core.agents.models import BuiltinAgentName

    if args.auto_approve and not args.agent:
        return BuiltinAgentName.AUTO_APPROVE, False
    return args.agent, args.auto_approve


def _session_intent(
    args: argparse.Namespace, *, allow_picker: bool
) -> LocalSessionIntent:
    from vibe.app_server.local import (
        ContinueSessionIntent,
        NewSessionIntent,
        ResumeSessionIntent,
    )

    if args.continue_session:
        return ContinueSessionIntent()
    if args.resume is True:
        if allow_picker:
            return NewSessionIntent()
        raise ValueError("--resume requires a session ID in programmatic mode")
    if isinstance(args.resume, str):
        return ResumeSessionIntent(args.resume)
    return NewSessionIntent()


def _run_programmatic_mode(args: argparse.Namespace, stdin_prompt: str | None) -> None:
    from vibe.app_server.local import ClientDescriptor, LocalHarnessOptions
    from vibe.app_server.protocol import (
        AppServerResponseError,
        ClientCapabilities,
        ClientInfo,
        SessionOptions,
    )
    from vibe.cli.programmatic import (
        OutputFormat,
        ProgrammaticLimitError,
        run_programmatic,
    )

    programmatic_prompt = args.prompt or stdin_prompt
    if not programmatic_prompt:
        print("Error: No prompt provided for programmatic mode", file=sys.stderr)
        sys.exit(1)
    output_format = OutputFormat(args.output if hasattr(args, "output") else "text")

    agent, auto_approve = _agent_selection(args)
    try:
        session_intent = _session_intent(args, allow_picker=False)
        final_response = run_programmatic(
            harness_options=LocalHarnessOptions(
                client=ClientDescriptor(
                    info=ClientInfo(
                        name="vibe_programmatic",
                        title="Vibe programmatic CLI",
                        version=__version__,
                        entrypoint="programmatic",
                        terminal_emulator=detect_terminal(),
                    ),
                    capabilities=ClientCapabilities(
                        callback_kinds=["approval", "user_input"]
                    ),
                ),
                session_options=SessionOptions(
                    cwd=str(Path.cwd()),
                    workspace_roots=list(args.add_dir),
                    agent=agent,
                    auto_approve=auto_approve,
                    enabled_tools=args.enabled_tools,
                    disabled_tools=[
                        *(args.disabled_tools or ()),
                        "ask_user_question",
                        "exit_plan_mode",
                    ],
                    max_turns=args.max_turns,
                    max_price=args.max_price,
                    max_session_tokens=args.max_tokens,
                    headless=True,
                    trust_workspace=bool(args.trust or args.worktree),
                ),
                session=session_intent,
            ),
            prompt=programmatic_prompt or "",
            output_format=output_format,
        )
        if final_response:
            print(final_response)
        sys.exit(0)
    except ProgrammaticLimitError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except AppServerResponseError as e:
        print(f"Error: {e.error.message}", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _run_interactive_mode(
    args: argparse.Namespace, stdin_prompt: str | None, *, autocopy_to_clipboard: bool
) -> None:
    from vibe.app_server.local import (
        ClientDescriptor,
        LocalHarness,
        LocalHarnessOptions,
    )
    from vibe.app_server.protocol import (
        AppServerResponseError,
        ClientCapabilities,
        ClientInfo,
        SessionOptions,
    )
    from vibe.cli.textual_ui.app import StartupOptions, run_textual_ui

    # --worktree runs in a checkout Vibe just made from the repo the user
    # launched from, and --trust is the user saying so outright. Both grant the
    # workspace session trust when the session is built, so prompting first
    # would ask about a decision already taken - and for --worktree it would
    # ask again for every new worktree, which is one per session.
    trust_workspace = bool(args.trust or args.worktree)

    agent, auto_approve = _agent_selection(args)

    harness = LocalHarness(
        LocalHarnessOptions(
            client=ClientDescriptor(
                info=ClientInfo(
                    name="vibe_tui",
                    title="Vibe Textual",
                    version=__version__,
                    entrypoint="cli",
                    terminal_emulator=detect_terminal(),
                ),
                capabilities=ClientCapabilities(
                    callback_kinds=["approval", "user_input"]
                ),
            ),
            session_options=SessionOptions(
                cwd=str(Path.cwd()),
                workspace_roots=list(args.add_dir),
                agent=agent,
                auto_approve=auto_approve,
                enabled_tools=args.enabled_tools,
                disabled_tools=list(args.disabled_tools or ()),
                trust_workspace=trust_workspace,
            ),
            session=_session_intent(args, allow_picker=True),
        )
    )
    try:
        summary = run_textual_ui(
            start_app_server=harness.connect,
            history_file=HISTORY_FILE.path,
            startup=StartupOptions(
                initial_prompt=args.initial_prompt or stdin_prompt,
                show_resume_picker=args.resume is True,
                is_resuming_session=(
                    args.continue_session or isinstance(args.resume, str)
                ),
                prompt_for_workspace_trust=not trust_workspace,
                autocopy_to_clipboard=autocopy_to_clipboard,
                resume_session_id=(
                    args.resume if isinstance(args.resume, str) else None
                ),
                continue_latest=bool(args.continue_session),
            ),
        )
    except AppServerResponseError as exc:
        rprint(f"[red]Error:[/] {exc.error.message}")
        sys.exit(1)
    print_session_resume_message(summary)


def run_cli(args: argparse.Namespace) -> None:
    load_dotenv_values()
    bootstrap_vibe_home()

    try:
        is_interactive = args.prompt is None
        orchestrator = load_config_orchestrator_or_exit()
        config = orchestrator.config
        stdin_prompt = get_prompt_from_stdin()
        if is_interactive:
            _run_interactive_mode(
                args=args,
                stdin_prompt=stdin_prompt,
                autocopy_to_clipboard=config.autocopy_to_clipboard,
            )
        else:
            _run_programmatic_mode(args=args, stdin_prompt=stdin_prompt)
    except (KeyboardInterrupt, EOFError):
        rprint("\n[dim]Bye![/]")
        sys.exit(0)
