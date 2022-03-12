import os
import shutil
import uuid
from pathlib import Path
from typing import Callable, Any

from refactoring_utils import RefactoringUtils
from workspace_client import WorkspaceClient

# Algorithm

# 1. before refactor: DONE
# 2. convert everything in a repo into files in staging area
# 3. operate on the refactoring
# 4. copy back to workspace
# 5. delete refactoring file manager and the staging path: DONE

# Staging path
# /tmp-refactor-${uniqueid}


class RefactoringController(object):
    def __init__(self, repo: str):
        api_url = os.getenv("API_URL")
        api_token = os.getenv("DB_TOKEN")
        self._repo = repo
        self._unique_id = str(uuid.uuid4())
        self._staging_path = Path(f"/tmp/refactor-{self._unique_id}")
        self._staging_path_str = str(self._staging_path)
        self.original_objs = None
        self.staging_objs = None

        self._client = WorkspaceClient(api_url=api_url, api_token=api_token)
        self._ref_util = RefactoringUtils(self._staging_path_str)

    def refactor(self, func: Callable[..., Any], *args, **kwargs):
        try:
            self.setup()

            # TODO: do the refactor
            changed_files = func(*args, **kwargs)

            # TODO: copy to the workspace
            for file in changed_files:
                print(file)
        finally:
            self.cleanup()

    def setup(self):
        # create staging folder
        self._create_staging_folder()
        self.get_all_objects()

    def _create_staging_folder(self):
        self._staging_path.mkdir(parents=True, exist_ok=True)

    def get_all_objects(self):
        self.original_objs, self.staging_objs = self.copy_to_staging(
            repo_dir=self._repo,
            parent_path=self._staging_path
        )

    # called before any refactoring is done
    def copy_to_staging(self, repo_dir: str, parent_path: Path):
        res = self._client.list(repo_dir)
        original_objs = res.get("objects", [])
        original_objs.sort(key=lambda x: x["path"])
        staging_objs = []

        for obj in original_objs:
            obj_type = obj["object_type"]
            obj_path = obj["path"]
            obj_name = Path(obj_path).name
            staging_obj = dict(obj)
            if obj_type == "NOTEBOOK":
                # export that as file to the correct module / directory
                # add python extension to the file name
                staging_path = parent_path.joinpath(f"{obj_name}.py")
                staging_obj["path"] = str(staging_path)
                self._client.export_source(obj["path"], staging_path)
            elif obj_type == "DIRECTORY":
                staging_path = parent_path.joinpath(obj_name)
                # create pkg on staging directory
                nested_mod = self.get_mod_from_path(staging_path)
                self._ref_util.create_pkg(nested_mod)

                # recursively list the contents in directory
                ori_children, staging_children = self.copy_to_staging(
                    repo_dir=obj_path,
                    parent_path=staging_path,
                )
                obj["children"] = ori_children
                staging_obj["path"] = str(staging_path)
                staging_obj["children"] = staging_children
            elif obj_type == "FILE":
                staging_path = parent_path.joinpath(obj_name)
                shutil.copyfile("/Workspace" + obj_path, staging_path)
                staging_obj["path"] = str(staging_path)
            staging_objs.append(staging_obj)

        return original_objs, staging_objs

    @staticmethod
    def get_mod_from_path(path: Path):
        return str(path).strip("/").replace("/", ".")

    # called after the refactoring is done
    def copy_to_workspace(self):
        # copy everything in staging area to workspace
        # delete files that no longer exist in staging area to workspace
        pass

    # only copy those which are affected by the refactor
    def copy_affected_files_to_workspace(self):
        pass

    def cleanup(self):
        shutil.rmtree(self._staging_path)
