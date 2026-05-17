"""
CIManager — GitHub Actions and repo management via GitHubAPI wrapper.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

_POLL_INTERVAL       = 10
_POLL_TIMEOUT        = 600
_POST_DISPATCH_DELAY = 6


class CIManager:
    def __init__(self, repo_owner: str, repo_name: str) -> None:
        self._owner = repo_owner
        self._repo  = repo_name

    def _api(self, token: str):
        from ....core.controllers.remote.github_api import GitHubAPI
        return GitHubAPI(self._owner, self._repo, direct_token=token)

    def dispatch_workflow(
        self,
        workflow_id: str,
        ref: str,
        token: str,
        on_status: Callable[[str], None],
        inputs: dict | None = None,
    ) -> None:
        def _run():
            try:
                api = self._api(token)
                resp = api.client.rest.actions.create_workflow_dispatch(
                    self._owner, self._repo, workflow_id,
                    body={"ref": ref, "inputs": inputs or {}},
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
                        resp = api.client.rest.actions.list_workflow_runs(
                            self._owner, self._repo, workflow_id, per_page=1,
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

    def list_workflows(self, token: str) -> list[dict]:
        api = self._api(token)
        resp = api.client.rest.actions.list_repo_workflows(self._owner, self._repo)
        api.update_rate_limit(resp.headers)
        return [
            {"id": wf.id, "name": wf.name, "path": wf.path,
             "state": wf.state, "html_url": wf.html_url}
            for wf in resp.parsed_data.workflows
        ]

    def list_tags(self, token: str, limit: int = 50) -> list[str]:
        api = self._api(token)
        resp = api.client.rest.repos.list_tags(self._owner, self._repo, per_page=limit)
        api.update_rate_limit(resp.headers)
        return [t.name for t in resp.parsed_data]

    def list_releases(self, token: str, limit: int = 10) -> list[dict]:
        api = self._api(token)
        resp = api.client.rest.repos.list_releases(self._owner, self._repo, per_page=limit)
        api.update_rate_limit(resp.headers)
        return [
            {"id": r.id, "tag_name": r.tag_name, "name": r.name or "",
             "published_at": str(r.published_at) if r.published_at else "",
             "html_url": r.html_url, "draft": r.draft, "prerelease": r.prerelease}
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
        api = self._api(token)
        resp = api.client.rest.repos.create_release(
            self._owner, self._repo,
            {"tag_name": tag, "name": name or tag, "body": body,
             "draft": draft, "prerelease": prerelease,
             "generate_release_notes": not bool(body)},
        )
        api.update_rate_limit(resp.headers)
        r = resp.parsed_data
        return {"id": r.id, "tag_name": r.tag_name, "name": r.name or "", "html_url": r.html_url}

    def list_branches(self, token: str) -> list[dict]:
        api = self._api(token)
        resp = api.client.rest.repos.list_branches(self._owner, self._repo, per_page=100)
        api.update_rate_limit(resp.headers)
        return [{"name": b.name, "protected": b.protected} for b in resp.parsed_data]

    def create_branch(self, name: str, from_sha: str, token: str) -> bool:
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
