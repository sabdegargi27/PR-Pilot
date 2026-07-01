from __future__ import annotations

import logging

from github import Github, GithubException, UnknownObjectException

from app.config import settings

logger = logging.getLogger(__name__)

# Lazily created so the module can be imported even when GITHUB_TOKEN is not
# yet set (e.g. during test collection).
_gh: Github | None = None


def _get_client() -> Github:
    global _gh
    if _gh is None:
        _gh = Github(settings.github_token)
    return _gh


def get_pull_request(repo_full_name: str, pr_number: int):
    repo = _get_client().get_repo(repo_full_name)
    return repo.get_pull(pr_number)


def post_review_comment(
    repo_full_name: str,
    pr_number: int,
    commit_id: str,
    path: str,
    line: int,
    body: str,
) -> None:
    gh = _get_client()
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)
    commit = repo.get_commit(commit_id)
    try:
        pr.create_review_comment(body=body, commit=commit, path=path, line=line, side="RIGHT")
    except GithubException as exc:
        raise RuntimeError(f"Failed to post GitHub comment: {exc}") from exc


def get_file_content(repo_full_name: str, path: str, ref: str) -> list[str]:
    """Return the file at *path*@*ref* as a list of lines.

    Returns an empty list (instead of raising) when the file does not exist at
    the given ref, cannot be fetched, or is not valid UTF-8 text.  Callers
    treat missing context as a soft failure.
    """
    repo = _get_client().get_repo(repo_full_name)
    try:
        contents = repo.get_contents(path, ref=ref)
    except UnknownObjectException:
        logger.warning("File not found in %s@%s: %s", repo_full_name, ref, path)
        return []
    except GithubException as exc:
        logger.warning("Could not fetch %s from %s: %s", path, repo_full_name, exc)
        return []

    try:
        return contents.decoded_content.decode("utf-8").splitlines()
    except (UnicodeDecodeError, AttributeError):
        logger.warning("Skipping binary or undecodable file: %s", path)
        return []
