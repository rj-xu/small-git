import os
import subprocess
from enum import StrEnum
from pathlib import Path
from shutil import rmtree
from typing import Annotated, cast

import git
import typer

app = typer.Typer()


repo = git.Repo(".")
assert repo.index.unmerged_blobs() == {}
# assert repo.git.stash("list") == ""

assert "origin" in repo.remotes
origin = repo.remotes["origin"]

if "master" in origin.refs:
    master = origin.refs["master"]
elif "main" in origin.refs:
    master = origin.refs["main"]
else:
    raise ValueError

my = repo.active_branch
assert my.name not in ("master", "main")

# config_reader = repo.config_reader()
# temp = config_reader.get_value("user", "name", default=None)
# assert isinstance(temp, str)
# user = temp

# temp = config_reader.get_value("user", "email", default=None)
# assert isinstance(temp, str)
# email = temp


def find_base(b0: git.Head = my, b1: git.Head = master):
    bases = repo.merge_base(b0, b1)
    assert len(bases) == 1
    return bases[0]


def is_dirty() -> bool:
    return repo.is_dirty(untracked_files=True)


def count_commits(c0: git.Commit, c1: git.Commit):
    return len(list(repo.iter_commits(f"{c0}..{c1}")))


# def has_conflict(c0: git.Commit, c1: git.Commit) -> bool:
#     return repo.git.merge_tree(c0.name, c1.name, quiet=True) != 0


# def commit_info(c: git.Commit):
#     return f"[ {c.message} ][ {c.author} ][ {c.authored_datetime} ][ {c.hexsha[:8]} ]"


class Cmd(StrEnum):
    # fmt: off
    COMMIT     = "💾 Commit"
    PULL       = "⬇️  Pull"
    PUSH       = "⬆️  Push"
    RESET      = "🪓 Reset"
    FORCE_PUSH = "⏫ Force-Push"
    SQUASH     = "🔨 Squash"
    ABORT      = "🛑 Abort"
    REBASE     = "🌳 Rebase"
    FETCH      = "🔃 Fetch"
    SYNC       = "🔄️ Sync"
    STASH      = "🗄️  Stash"
    SUBMOD     = "📦 Submodule"
    SCOOP      = "🥄 Scoop"
    ENV        = "🌏 Env"
    DELETE     = "🗑️  Delete"
    CHECK      = "🚓 Check"
    # fmt: on

    def start(self):
        typer.echo(f"{self} START")

    def end(self):
        typer.secho(f"{self} END", fg=typer.colors.GREEN)

    def cancel(self):
        typer.secho(f"{self} CANCELLED", fg=typer.colors.YELLOW)

    def fail(self, e: Exception):
        typer.echo(e)
        typer.secho(f"{self} FAILED", bg=typer.colors.RED)

    def info(self, msg: str):
        typer.echo(f"{self}: {msg}")

    def warn(self, msg: str):
        typer.secho(f"🚨 {msg}", bg=typer.colors.YELLOW)

    def error(self, msg: str):
        return RuntimeError(f"💥 {msg}")

    def confirm(self, msg: str) -> bool:
        s = typer.style(f"✅ {msg}", bg=typer.colors.BLUE)
        return typer.confirm(s)

    def run(self, cmds: str | list[str], *, use_proxy: bool = False):
        if use_proxy:
            proxy = "http://10.3.6.15:3128"
            env = os.environ.copy()
            env["HTTP_PROXY"] = proxy
            env["HTTPS_PROXY"] = proxy
        else:
            env = None

        if isinstance(cmds, str):
            cmds = [cmds]
        for c in cmds:
            self.info(f"{c}")
            subprocess.run(c, check=True, shell=True, capture_output=False, text=True, env=env)  # noqa: S602


@app.command()
def show():
    for cmd in Cmd:
        cmd.start()


@app.command()
def commit(msg: Annotated[str, typer.Argument()] = "update") -> None:
    if not is_dirty():
        return

    cmd = Cmd.COMMIT
    cmd.start()

    cmd.info(f"Message: {msg}")
    if not repo.index.diff("HEAD"):
        repo.git.add(A=True)
    repo.index.commit(msg)

    cmd.end()


def pull() -> None:
    cmd = Cmd.PULL
    cmd.start()
    origin.pull(rebase=True, autostash=True)
    cmd.end()


def push() -> None:
    cmd = Cmd.PUSH
    cmd.start()
    origin.push(my.name)
    cmd.end()


def reset_to(c: git.Commit, *, need_commit: bool = True) -> None:
    if my.commit == c:
        return

    cmd = Cmd.RESET
    cmd.start()
    repo.git.reset(c)
    cmd.end()

    if need_commit:
        commit(f"reset to {c.hexsha[:8]}")


@app.command()
def reset() -> None:
    base = find_base()
    reset_to(base, need_commit=False)
    Cmd.RESET.warn(f"You need to {Cmd.COMMIT} and {Cmd.FORCE_PUSH} later")


@app.command()
def force_push() -> bool:
    cmd = Cmd.FORCE_PUSH
    cmd.start()

    try:
        origin.push(my.name, force_with_lease=True)
    except git.GitCommandError as e:
        cmd.fail(e)
        if (
            cmd.confirm("Someone commited into your-origin, OVERWRITE his code?")
            and cmd.confirm("His code may be usefull, continue?")
            and cmd.confirm("Are you sure?")
        ):
            # origin.push(my.name, force=True)
            raise cmd.error("Input: git push --force") from e
        cmd.cancel()
        return False

    cmd.end()
    return True


@app.command()
def squash() -> None:
    cmd = Cmd.SQUASH
    cmd.start()
    base = find_base()
    reset_to(base)
    force_push()
    cmd.end()


@app.command()
def abort() -> None:
    rebase_merge_dir = Path(repo.git_dir) / "rebase-merge"
    rebase_apply_dir = Path(repo.git_dir) / "rebase-apply"

    in_rebase = rebase_merge_dir.exists() or rebase_apply_dir.exists()

    if not in_rebase:
        return

    cmd = Cmd.ABORT
    cmd.start()

    try:
        repo.git.rebase(abort=True)
    except git.GitCommandError as e:
        cmd.fail(e)
        raise cmd.error("You need to find help") from e

    cmd.end()


def rebase_to(c: git.Commit) -> bool:
    cmd = Cmd.REBASE
    cmd.start()

    try:
        repo.git.rebase(c, autostash=True)
    except git.GitCommandError as e:
        cmd.fail(e)
        return False

    cmd.end()
    return True


def try_rebase(c: git.Commit, base: git.Commit) -> bool:
    cmd = Cmd.REBASE

    if rebase_to(c):
        return True
    abort()

    cmd.warn("Found 💣 Conflict")
    if cmd.confirm(f"{Cmd.RESET} and {Cmd.REBASE} again?"):
        reset_to(base)
        if not rebase_to(c):
            raise cmd.error(f"You need to resolve conflict manually, then {Cmd.SYNC}")
        return True
    cmd.cancel()
    return False


def fetch() -> None:
    cmd = Cmd.FETCH
    cmd.start()
    origin.fetch(prune=True, tags=True, prune_tags=True)
    cmd.end()


@app.command()
def sync() -> bool:
    cmd = Cmd.SYNC
    cmd.start()

    fetch()

    base = find_base()

    if my.name not in origin.refs:
        if base == master.commit or try_rebase(master.commit, base):
            push()
        else:
            cmd.warn("You need to choose {Cmd.RESET} and {Cmd.REBASE}")
            cmd.cancel()
            return False
    else:
        if base != master.commit:
            cmd.warn("Your branch is out-of-date, need to {Cmd.REBASE} later")

        my_origin = origin.refs[my.name]

        my_ahead = count_commits(my_origin.commit, my.commit)
        my_origin_ahead = count_commits(my.commit, my_origin.commit)

        if my_ahead > 0 and my_origin_ahead == 0:
            cmd.info(f"{Cmd.PUSH} your branch")
            push()
        elif my_ahead == 0 and my_origin_ahead > 0:
            cmd.info(f"{Cmd.PULL} your-origin branch")
            pull()
        elif my_ahead > 0 and my_origin_ahead > 0:
            cmd.warn("Found 🍴 Fork")

            # NOTE: never rebase others banch
            if (base.committed_datetime > find_base(my_origin, master).committed_datetime) or (
                cmd.confirm(f"{Cmd.FORCE_PUSH} your branch?")
            ):
                force_push()
            elif (cmd.confirm(f"{Cmd.PULL} your-origin branch?")) and (
                try_rebase(my_origin.commit, find_base(my, my_origin))
            ):
                if my.commit != my_origin.commit:
                    push()
            else:
                cmd.warn(f"You need to choose {Cmd.FORCE_PUSH} or {Cmd.PULL}")
                cmd.cancel()
                return False
        else:
            cmd.info("Your-origin branch is already up-to-date")

    cmd.end()
    return True


@app.command()
def rebase() -> None:
    if not sync():
        return

    base = find_base()
    if base == master.commit:
        return

    # origin.pull(master.name, rebase=True, autostash=True)
    if try_rebase(master.commit, base):
        force_push()


@app.command()
def stash() -> None:
    stash_cnt = len(cast("str", repo.git.stash("list")).splitlines())

    cmd = Cmd.STASH
    cmd.start()

    if stash_cnt == 1 and cmd.confirm("Do you want to Pop?"):
        repo.git.stash("pop")
        cmd.end()
    elif stash_cnt == 0 and cmd.confirm("Do you want to Stash?"):
        repo.git.stash("push")
        cmd.end()
    else:
        cmd.cancel()


@app.command()
def submod(*, remote: bool = False) -> None:
    if not sync():
        return

    cmd = Cmd.SUBMOD
    cmd.start()
    args = ["update", "--init", "--recursive", "--force"]
    if remote:
        cmd.warn("Update all submodules to remote HEAD")
        args.append("--remote")
    try:
        repo.git.submodule(args)
    except git.GitCommandError as e:
        cmd.fail(e)
        raise cmd.error("You need to find help") from e
    cmd.end()


@app.command()
def zen() -> None:
    z = [
        "Always keep tree-like structure, linear history",
        "始终保持树形结构, 线性历史",
        "One commit doesn't matter, all commits matter",
        "一次修改无关紧要, 总的修改才重要",
        "Only 3 branches: yours, your-origin and master",
        "只有 3 个分支: 你的分支, 你的远程分支和主分支",
        "Take ownership of your branch",
        "自己的分支自己负责",
        r"         ",
        r"    |    ",
        r"    ●    ",
        r" |  |    ",
        r" ●  ●    ",
        r"  \ |  | ",
        r"    ●  ● ",
        r"    | /  ",
        r"    ●    ",
        r"    |    ",
        r"         ",
    ]
    for line in z:
        typer.echo(line)


@app.command()
def scoop() -> None:
    cmd = Cmd.SCOOP
    cmd.start()
    cmd.run("powershell scripts/install_scoop.ps1")
    cmd.end()


@app.command()
def env() -> None:
    cmd = Cmd.ENV
    cmd.start()
    cmd.run("uv sync")
    cmd.end()


@app.command()
def delete() -> None:
    cmd = Cmd.DELETE
    cmd.start()

    dirs = [Path("logs"), Path("output")]
    for d in dirs:
        if d.exists():
            rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        gitkeep.touch()

    force_dirs = [Path("MsCamRegLog")]
    for d in force_dirs:
        if d.exists():
            rmtree(d)

    cmd.end()


@app.command()
def check(dirs: Annotated[str, typer.Argument()] = "src tests") -> None:
    cmd = Cmd.CHECK
    cmd.start()

    venv = Path(".venv") / "Scripts"
    ruff = venv / "ruff"
    pyright = venv / "pyright"
    py = venv / "python"
    try:
        cmd.run(f"{ruff} check {dirs} --fix")
        cmd.run(f"{pyright} {dirs} --pythonpath {py}")
    except subprocess.CalledProcessError as e:
        cmd.fail(e)
        return
    cmd.end()


if __name__ == "__main__":
    app()
