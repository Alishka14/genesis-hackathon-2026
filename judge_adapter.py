"""Genesis FinTech judge entry points. Run only in the trusted evaluator process."""
from pathlib import Path
import tempfile

from ledgergym import generator
from ledgergym.canonical import JudgeEnv, score_episode
from ledgergym.episode_io import export_episode


def generate_episode(seed, config, output_dir):
    public, truth = generator.generate_episode(seed, config)
    dest = Path(output_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Stage a complete export before handing either component to the judge.
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        staged = Path(tmp) / "episode"
        export_episode(staged, public, truth, seed=seed)
        if not dest.exists():
            staged.rename(dest)
        elif dest.is_dir() and not any(dest.iterdir()):
            (staged / "private").rename(dest / "private")
            try:
                (staged / "public").rename(dest / "public")
            except OSError:
                (dest / "private").rename(staged / "private")
                raise
        else:
            raise FileExistsError("output directory must be empty")


def make_env():
    return JudgeEnv()


__all__ = ["generate_episode", "make_env", "score_episode"]
