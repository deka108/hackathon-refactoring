import os
import shutil
import uuid
from pathlib import Path
from typing import Callable, Any

from refactor import RefactoringUtils
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
    def __init__(self, repo: str, api_url=os.getenv("API_URL"), api_token=os.getenv("DB_TOKEN")):
        """

        Parameters
        ----------
        repo: The Workspace Repo path, eg: /Repos/[username]/[repo]
        """
        self._repo = repo
        self._unique_id = str(uuid.uuid4())
        self._staging_path = Path(f"/tmp/refactor-{self._unique_id}")
        self._staging_path_str = str(self._staging_path)
        # may not need these
        self.original_objs = None
        self.staging_objs = None
        # map staging path to original path
        self.staging_idx = {}
        # map original path to the workspace object
        self.original_idx = {}

        self._client = WorkspaceClient(api_url=api_url, api_token=api_token)
        self._ref_util = RefactoringUtils(self._staging_path_str)

    def refactor(self, func: Callable[..., Any], *args, **kwargs):
        try:
            self.setup()

            # TODO: do the refactor
            # the refactor may modify exist files, create new files or remove files
            changed_files = func(*args, **kwargs)

            self.copy_affected_files_to_workspace()

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
            parent_staging_dir=self._staging_path,
            parent_dir=""
        )

    # called before any refactoring is done
    def copy_to_staging(self, repo_dir: str, parent_staging_dir: Path, parent_dir: str):
        res = self._client.list(repo_dir)
        original_objs = res.get("objects", [])
        original_objs.sort(key=lambda x: x["path"])
        staging_objs = []

        for obj in original_objs:
            # original obj
            obj_type = obj["object_type"]
            obj_path = obj["path"]
            obj_name = Path(obj_path).name

            # staging obj
            staging_obj = dict(obj)
            staging_path = ""

            if obj_type == "NOTEBOOK":
                # export that as file to the correct module / directory
                # add python extension to the file name
                staging_path = parent_staging_dir.joinpath(f"{obj_name}.py")
                self._client.export_source(obj["path"], staging_path)
            elif obj_type == "DIRECTORY":
                staging_path = parent_staging_dir.joinpath(obj_name)
                # create pkg on staging directory
                if parent_dir != "":
                    nested_parent_dir = f"{parent_dir}/{obj_name}"
                else:
                    nested_parent_dir = obj_name
                nested_mod = self._ref_util.get_mod_from_path(nested_parent_dir)
                self._ref_util.create_pkg(nested_mod)

                # recursively list and get the contents in directory
                ori_children, staging_children = self.copy_to_staging(
                    repo_dir=obj_path,
                    parent_staging_dir=staging_path,
                    parent_dir=nested_parent_dir
                )
                obj["children"] = ori_children
                staging_obj["children"] = staging_children
            elif obj_type == "FILE":
                staging_path = parent_staging_dir.joinpath(obj_name)
                shutil.copyfile("/Workspace" + obj_path, staging_path)

            # update staging object and index
            staging_key = str(staging_path)
            staging_obj["path"] = staging_key
            self.staging_idx[staging_key] = obj_path
            staging_objs.append(staging_obj)

            # update original index
            self.original_idx[obj_path] = obj

        return original_objs, staging_objs

    # called after the refactoring is done
    def copy_to_workspace(self):
        # copy everything in staging area to workspace
        # delete files that no longer exist in staging area to workspace
        pass

    # only copy those which are affected by the refactor
    def copy_affected_files_to_workspace(self, changed_files):
        # get the affected files: if it exists in staging_idx re-upload them
        # otherwise create new file and/or module (copy)
        for changed_path in changed_files:
            if changed_path in self.staging_idx:
                ws_path = self.staging_idx[changed_path]
                if ws_path in self.original_idx:
                    obj_type = self.original_idx[ws_path]["object_type"]
                    # if it's a notebook
                    if obj_type == "NOTEBOOK":
                        self._client.import_source(ws_path, changed_path)
                    # if it's a file
                    elif obj_type == "FILE":
                        shutil.copyfile(changed_path, "/Workspace" + ws_path)
            else:
                # map the changed_path into workspace path:
                #
                # changed path doesn't exist in original paths
                # create new modules if necessary
                # import source
                pass
        # check if there are additional files not in repo
        # algo:
        # list all files in staging dir
            # see if they are in staging_idx
            # if doesn't exist, mkdirs / upload to workspace
        # check if there are files removed from the repo
            # get the keys in staging_idx subtract it from list of files in staging dir
        pass

    def cleanup(self):
        shutil.rmtree(self._staging_path)

    @staticmethod
    def tree_dir(path: str):
        filetree = []
        for dirname, dirnames, filenames in os.walk(path):
            # print path to all subdirectories first.
            for subdirname in dirnames:
                filetree.append(os.path.join(dirname, subdirname))

            # print path to all filenames.
            for filename in filenames:
                filetree.append(os.path.join(dirname, filename))
        filetree.sort()
        return filetree
