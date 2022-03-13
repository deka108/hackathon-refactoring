import ast
from itertools import accumulate
from pathlib import Path
from typing import List, Optional

from rope.base.change import ChangeSet
from rope.base.exceptions import RopeError
from rope.base.project import Project
from rope.base import libutils
from rope.base.pyobjectsdef import PyModule
from rope.base.resources import Resource
from rope.contrib.generate import create_package, create_module
from rope.refactor import move
from rope.refactor.occurrences import Finder, Occurrence


# - path is relative to the root
# - real_path is the absolute path


class RefactoringUtils(object):
    def __init__(self, root: str):
        self.root = root
        self._project = Project(self.root)
    
    @staticmethod
    def _get_functions_from_pymod(pymod: PyModule) -> List[str]:
        funcs = []
        for name, item in pymod.get_attributes().items():
            try:
                item_ast = item.get_object().get_ast()
                if isinstance(item_ast, ast.FunctionDef):
                    funcs.append(name)
                elif isinstance(item_ast, ast.ClassDef):
                    funcs.append(name)
            except AttributeError:
                pass
        return funcs
    
    def find_functions_on_script(self, code_str: str) -> List[str]:
        py_mod = libutils.get_string_module(self._project, code_str)
        return self._get_functions_from_pymod(py_mod)

    def find_functions_on_file(self, file_path: str) -> List[str]:
        """Get the functions of a relative path to the Project.

        Parameters
        ----------
        file_path: relative to project root.

        Returns
        -------

        """
        res = self._project.get_resource(file_path)
        py_mod = self._project.get_module(libutils.modname(res))
        return self._get_functions_from_pymod(py_mod)

    def create_pkg(self, pkg_name: str):
        try:
            create_package(self._project, pkg_name)
        except RopeError as exc:
            if "already exists" in str(exc):
                pass
            else:
                raise

    def create_module(self, module_name: str):
        try:
            create_module(self._project, module_name)
        except RopeError as exc:
            if "already exists" in str(exc):
                pass
            else:
                raise

    def _find_function(self, src_res: Resource, function_name: str) -> Optional[Occurrence]:
        finder = Finder(self._project, function_name)
        for occ in finder.find_occurrences(resource=src_res):
            return occ

    @staticmethod
    def get_mod_from_path(path: Path):
        return str(path).strip("/").replace("/", ".")

    def get_or_create_resource(self, path: str):
        base_path = self._project.root.real_path

        # if resource doesn't exist, create the module and/or parent subdirs first
        if not Path(base_path + path).exists():
            full_mod = ""
            # check if it contains subdirs first
            if Path(path).parent != ".":
                # create the subdir first using rope to create pkgs
                parent_mod = self.get_mod_from_path(Path(path).parent)
                for mod in accumulate(parent_mod.split("."), lambda x, y: f"{x}.{y}"):
                    try:
                        self._project.get_module(mod)
                    except ModuleNotFoundError:
                        create_package(self._project, mod)

            # check if it is a module or a package
            # module --> .py, package is only name
            if Path(path).suffix == "":
                full_mod = self.get_mod_from_path(Path(path))
                create_package(self._project, full_mod)
            else:
                full_mod = self.get_mod_from_path(Path(path).with_suffix(""))
                create_module(self._project, full_mod)

        return self._project.get_resource(path)

    # this is local filepath on staging
    def move_functions(self, src_path: str, func_names: List[str], dest_path: str) -> (ChangeSet, List[Resource]):
        """

        Parameters
        ----------
        src_path: relative to project root
        func_names: list of function names
        dest_path: relative to project root

        Returns
        -------

        """
        # relative to project root
        src_res = self._project.get_resource(src_path)
        # may modify the staging directory: adding new files
        dest_res = self.get_or_create_resource(dest_path)

        changed_files = []
        # iterate over the function, move them one by one
        for func_name in func_names:
            occ = self._find_function(src_res, func_name)
            if occ:
                mover = move.create_move(self._project, src_res, occ.offset)
                changes = mover.get_changes(dest_res)
                self._project.do(changes)
                # changed_file's path is relative to the staging directory, so it should be identical as the repos
                for changed_file in changes.get_changed_resources():
                    changed_files.append(changed_file)

        return changes, changed_files
