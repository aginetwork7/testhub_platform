"""事件素材的两个根：受版本管理的基准集，与运行时可写的上传集。

`data_warehouse/events/` 此前同时承担两个互相冲突的角色：它既是每个环境都需要、变更应当可评审
的**基准素材集**，又是界面上传端点的**写入目标**。后果是上传一个素材就让 git 工作区变脏；在正式
环境尤其要命——`/home/agi7/testhub_platform` 本身是 git 工作区，工作区变脏会让下一次部署的
`git pull` 因本地改动冲突而失败。

因此把两个角色拆开：基准集留在代码库里只读，上传集写到 `MEDIA_ROOT` 下（已被 gitignore 覆盖）。
读取时两个根一起枚举，同名以上传集优先，使用户可以覆盖基准素材而不必改代码库。
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

# 基准素材集：随代码分发，新环境开箱即用，变更走代码评审。运行时只读。
BASELINE_ROOT = (Path(__file__).resolve().parent / 'data_warehouse' / 'events')


def upload_root() -> Path:
    """用户通过界面上传的素材根。位于 MEDIA_ROOT 之下，不受版本管理。"""
    return Path(settings.MEDIA_ROOT) / 'data_factory' / 'events'


def ensure_upload_root(category: str = '') -> Path:
    """返回上传根（或其下的某个分类目录），并确保它存在。"""
    target = upload_root() / category if category else upload_root()
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_roots() -> list[Path]:
    """读取时枚举的根，顺序即优先级：上传集在前，可覆盖同名的基准素材。

    顺序是固定的而不是依赖文件系统返回序，否则界面上的素材列表会无缘无故抖动。
    """
    return [upload_root(), BASELINE_ROOT]


def is_baseline(path: Path) -> bool:
    """该路径是否属于基准素材集。基准素材不允许通过界面删除。"""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    baseline = BASELINE_ROOT.resolve()
    return resolved == baseline or baseline in resolved.parents


def resolve_within(root: Path, relative_path: str) -> Path | None:
    """把相对路径解析到根之下；越界时返回 None，防目录穿越。"""
    try:
        root_resolved = root.resolve()
        candidate = (root_resolved / relative_path).resolve()
    except OSError:
        return None
    if candidate != root_resolved and root_resolved not in candidate.parents:
        return None
    return candidate


def locate(relative_path: str) -> Path | None:
    """按读取优先级找出这个相对路径对应的实际文件，找不到返回 None。"""
    for root in read_roots():
        candidate = resolve_within(root, relative_path)
        if candidate is not None and candidate.exists():
            return candidate
    return None


def categories() -> list[str]:
    """两个根下的全部分类目录名，去重后按名称排序。"""
    names: set[str] = set()
    for root in read_roots():
        if not root.is_dir():
            continue
        names.update(path.name for path in root.iterdir() if path.is_dir())
    return sorted(names)
