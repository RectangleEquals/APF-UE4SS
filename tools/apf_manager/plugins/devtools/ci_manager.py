"""
CIManager — GitHub Actions and repo management via GitHubAPI wrapper.

All public methods except dispatch_workflow() are synchronous.
Callers wrap them in background threads.

dispatch_workflow() is already background-threaded (on_status callback pattern).
"""

from __future__ import annotations

import threading
import time
from typing import Callable

_POLL_INTERVAL       = 10   # seconds between status polls
_POLL_TIMEOUT        = 600  # seconds before giving up (10 minutes)
_POST_DISPATCH_DELAY = 6    # seconds to wait before first poll (GitHub needs time to queue)


class CIManager:
    def __init__(self, repo_owner: str, repo_name: str) -> None:
        self._owner = repo_owner
        self._repo  = repo_name

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _api(self, token: str):
        """Return a GitHubAPI instance using the given token directly."""
        from ...core.remote.github_api import GitHubAPI
        return GitHubAPI(self._owner, self._repo, direct_token=token)

    # -----------------------------------------------------------------------
    # Workflows — dispatch + poll
    # -----------------------------------------------------------------------

    def dispatch_workflow(
        self,
        workflow_id: str,
        ref: str,
        token: str,
        on_status: Callable[[str], None],
        inputs: dict | None = None,
    ) -> None:
        """
        Dispatch a workflow and poll for completion in a background thread.

        workflow_id may be the workflow filename (e.g. "build.yml") or its
        numeric GitHub ID as a string.

        on_status(status) is called with:
          "dispatched"                        — dispatch accepted
          "queued" / "in_progress"            — run is queued or running
          "success"                           — run completed successfully
          "failure" / "cancelled" / "skipped" / "timed_out" — terminal failure states
          "error: <msg>"                      — API or network error
          "poll_timeout"                      — gave up after _POLL_TIMEOUT seconds
        """
        def _run():
            try:
                api = self._api(token)

                resp = api.client.rest.actions.create_workflow_dispatch(
                    self._owner, self._repo, workflow_id,
                    {"ref": ref, "inputs": inputs or {}},
                )
                try:
                    api.update_rate_limit(resp.headers)
                except Exception:
                    pass
                on_status("dispatched")

                time.sleep(_POST_DISPATCH_DELAY)

                deadline = time.monotonic() + _POLL_TIMEOUT
                while time.monotonic() < deadline:
                    try:
                        # Poll runs for this specific workflow (more accurate than repo-wide)
                        resp = api.client.rest.actions.list_workflow_runs(
                            self._owner, self._repo, workflow_id,
                            per_page=1,
                        )
                        api.update_rate_limit(resp.headers)
                        runs = resp.parsed_data.workflow_runs
                        if runs:
                            run        = runs[0]
                            status     = run.status     or "queued"
                            conclusion = run.conclusion or ""

                            if status == "completed":
                                on_status(conclusion or "unknown")
                                return

                            on_status(status)
                    except Exception as exc:
                        on_status(f"error: {exc}")
                        return

                    time.sleep(_POLL_INTERVAL)

                on_status("poll_timeout")

            except Exception as exc:
                on_status(f"error: {exc}")

        threading.Thread(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # Workflows — list + recent runs
    # -----------------------------------------------------------------------

    def list_workflows(self, token: str) -> list[dict]:
        """
        Return all workflows in the repo.
        Each dict: {id, name, path, state, html_url}
        """
        api = self._api(token)
        resp = api.client.rest.actions.list_repo_workflows(self._owner, self._repo)
        api.update_rate_limit(resp.headers)
        workflows = resp.parsed_data.workflows
        return [
            {
                "id":       wf.id,
                "name":     wf.name,
                "path":     wf.path,
                "state":    wf.state,
                "html_url": wf.html_url,
            }
            for wf in workflows
        ]

    def list_recent_runs(self, workflow_id: int | str, token: str, limit: int = 5) -> list[dict]:
        """
        Return recent runs for a specific workflow.
        Each dict: {id, status, conclusion, created_at, html_url, head_branch}
        """
        api = self._api(token)
        resp = api.client.rest.actions.list_workflow_runs(
            self._owner, self._repo, workflow_id,
            per_page=limit,
        )
        api.update_rate_limit(resp.headers)
        runs = resp.parsed_data.workflow_runs
        return [
            {
                "id":          r.id,
                "status":      r.status or "",
                "conclusion":  r.conclusion or "",
                "created_at":  str(r.created_at) if r.created_at else "",
                "html_url":    r.html_url or "",
                "head_branch": r.head_branch or "",
            }
            for r in runs
        ]

    def cancel_run(self, run_id: int, token: str) -> bool:
        """Cancel a running workflow run. Returns True on success."""
        try:
            api = self._api(token)
            resp = api.client.rest.actions.cancel_workflow_run(self._owner, self._repo, run_id)
            try:
                api.update_rate_limit(resp.headers)
            except Exception:
                pass
            return True
        except Exception:
            return False

    # -----------------------------------------------------------------------
    # Tags
    # -----------------------------------------------------------------------

    def list_tags(self, token: str, limit: int = 50) -> list[str]:
        """Return tag names (most recent first, up to limit)."""
        api = self._api(token)
        resp = api.client.rest.repos.list_tags(self._owner, self._repo, per_page=limit)
        api.update_rate_limit(resp.headers)
        return [t.name for t in resp.parsed_data]

    # -----------------------------------------------------------------------
    # Releases
    # -----------------------------------------------------------------------

    def list_releases(self, token: str, limit: int = 10) -> list[dict]:
        """
        Return recent releases.
        Each dict: {id, tag_name, name, published_at, html_url, draft, prerelease}
        """
        api = self._api(token)
        resp = api.client.rest.repos.list_releases(self._owner, self._repo, per_page=limit)
        api.update_rate_limit(resp.headers)
        return [
            {
                "id":           r.id,
                "tag_name":     r.tag_name,
                "name":         r.name or "",
                "published_at": str(r.published_at) if r.published_at else "",
                "html_url":     r.html_url,
                "draft":        r.draft,
                "prerelease":   r.prerelease,
            }
            for r in resp.parsed_data
        ]

    def create_release(
        self,
        tag: str,
        name: str,
        body: str,
        token: str,
        draft: bool = False,
        prerelease: bool = False,
    ) -> dict:
        """
        Create a GitHub release. Returns the release dict on success.
        Raises on API error.
        """
        api = self._api(token)
        resp = api.client.rest.repos.create_release(
            self._owner, self._repo,
            {
                "tag_name":               tag,
                "name":                   name or tag,
                "body":                   body,
                "draft":                  draft,
                "prerelease":             prerelease,
                "generate_release_notes": not bool(body),
            },
        )
        api.update_rate_limit(resp.headers)
        r = resp.parsed_data
        return {
            "id":       r.id,
            "tag_name": r.tag_name,
            "name":     r.name or "",
            "html_url": r.html_url,
        }

    # -----------------------------------------------------------------------
    # Branches
    # -----------------------------------------------------------------------

    def list_branches(self, token: str) -> list[dict]:
        """
        Return all branches.
        Each dict: {name, protected}
        """
        api = self._api(token)
        resp = api.client.rest.repos.list_branches(self._owner, self._repo, per_page=100)
        api.update_rate_limit(resp.headers)
        return [
            {
                "name":      b.name,
                "protected": b.protected,
            }
            for b in resp.parsed_data
        ]

    def create_branch(self, name: str, from_sha: str, token: str) -> bool:
        """Create a branch pointing at from_sha. Returns True on success."""
        try:
            api = self._api(token)
            resp = api.client.rest.git.create_ref(
                self._owner, self._repo,
                {"ref": f"refs/heads/{name}", "sha": from_sha},
            )
            try:
                api.update_rate_limit(resp.headers)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def delete_branch(self, name: str, token: str) -> bool:
        """Delete a branch by name. Returns True on success."""
        try:
            api = self._api(token)
            resp = api.client.rest.git.delete_ref(self._owner, self._repo, f"heads/{name}")
            try:
                api.update_rate_limit(resp.headers)
            except Exception:
                pass
            return True
        except Exception:
            return False
