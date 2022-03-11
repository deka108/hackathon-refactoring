from rope.base.project import Project
from rope.base import libutils
from rope.refactor import move
from rope.refactor.move import MoveMethod


class RefactoringUtils(object):
    def __init__(self, root):
        self.root = root
        self._project = Project(self.root)
    
    @staticmethod
    def _get_functions_from_pymod(self, pymod):
        funcs = []
        for name, item in pymod.get_attributes().items():
            if item.get_object().get_kind() == "function":
                funcs.append(name)
        return funcs
    
    def find_functions_on_script(self, code_str):
        py_mod = libutils.get_string_module(self._project, code_str)
        return self._get_functions_from_pymod(py_mod)
    
    def find_functions_on_file(self, file_path):
        res = project.get_resource(file_path)
        py_mod = project.get_module(libutils.modname(res))
        return self._get_functions_from_pymod(py_mod)
    
    def find_functions_on_notebook(self, notebook_path):
        # find the equivalent path in staging based on the database
        return self.find_functions_on_file(file_path)
    
    def move_functions(self, src_path, func_names, dest_path):
        # iterate over the function, move them one by one
        src_res = project.get_resource(file_path)
        
        # TODO: check if it exist, otherwise create assets / modify db 
        dst_res = project.get_resource(file_path)
        
        for occ in finder.occurences():
            mover = move.create_move(self._project, src_res, occ.offset)
            changes = mover.get_changes(dest_res)
            self._project.do(changes)
        
