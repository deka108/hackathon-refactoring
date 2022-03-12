import os
import shutil
import uuid
from pathlib import Path
from typing import Callable, Any, List

from rope.base.resources import Resource

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
    def __init__(self, repo: str, api_url=os.getenv("API_URL"), api_token=os.getenv("DB_TOKEN"), base_workspace_dir="/Workspace"):
        """

        Parameters
        ----------
        repo: The Workspace Repo path, eg: /Repos/[username]/[repo]
        """
        self._repo = repo
        self._unique_id = str(uuid.uuid4())
        self.base_workspace_dir = base_workspace_dir
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
            changed_resources = func(*args, **kwargs)

            self.copy_to_workspace(changed_resources)
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
                shutil.copyfile(self.base_workspace_dir + obj_path, staging_path)

            # update staging object and index
            staging_key = str(staging_path)
            staging_obj["path"] = staging_key
            self.staging_idx[staging_key] = obj_path
            staging_objs.append(staging_obj)

            # update original index
            self.original_idx[obj_path] = obj

        return original_objs, staging_objs

    def is_notebook(self, path):
        with open(path) as f:
            first_line = f.readline()
            return "# Databricks notebook source" in first_line

    @staticmethod
    def remove_prefix(text, prefix):
        return text[len(prefix):]

    # only copy those which are affected by the refactor
    def copy_to_workspace(self, changed_files: List[Resource]):
        # algorithm
        # 1. get the deleted and modified set
        # 2. for each modified: upload to Repo
        # 3. for each deleted: delete from Repo

        # data: set of relative paths (to staging path --> will be mapped to a Repo path by prepending the Repo)
        mod_or_created_set = set()
        deleted_set = set()

        # get the modified or created set vs delete set from changed_files
        for changed_src in changed_files:
            if changed_src.exists():
                mod_or_created_set.add(changed_src.path)
            else:
                deleted_set.add(changed_src.path)

        # add to created set: get the ones that exist in changed but not in Repos
        # repos paths --> drop the repos prefix
        repos_paths = set(self.original_idx.keys())
        repos_paths = set(self.remove_prefix(p, self._repo + "/") for p in repos_paths)

        # staging paths --> drop the staging paths prefix
        staging_paths = set(self.staging_idx.keys())
        staging_paths = set(self.remove_prefix(p, self._staging_path_str + "/") for p in staging_paths)

        # get the modified / created set: the ones exist in staging but not in repo
        mod_or_created_set = mod_or_created_set | staging_paths.difference(repos_paths)
        mod_or_created_set = sorted(mod_or_created_set)

        # add to deleted set: get the ones that exist in Repos but not in staging
        deleted_set = deleted_set | repos_paths.difference(staging_paths)
        deleted_set = sorted(deleted_set)

        # create or modified: exist in staging, may or may not exist in repo
        for path in mod_or_created_set:
            staging_path = self._staging_path.joinpath(path)
            ws_path_key = f"{self._repo}/{path}"

            if staging_path.is_dir():
                self._client.mkdirs(ws_path_key)
            elif self.is_notebook(staging_path):
                self._client.import_source(ws_path_key, str(staging_path))
            elif staging_path.is_file():
                shutil.copyfile(staging_path, self.base_workspace_dir + ws_path_key)

        # deleted: doesn't exist in staging
        for i, path in enumerate(deleted_set):
            ws_path_key = f"{self._repo}/{path}"
            # optimization: if the parent path is already deleted then we don't need to delete
            self._client.delete(ws_path_key, recursive=True)

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
