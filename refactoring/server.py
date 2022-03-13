import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from fastapi.params import Query
from pydantic import BaseModel, conlist, Field
from typing import List

from controller import RefactoringController

# listing functions
list_route = APIRouter()


class Content(BaseModel):
    content: str = Field(..., description="The source code string.")


class ListOfFunctions(BaseModel):
    functions: List[str] = Field(..., description="The List of Function and Names in the File.")


@list_route.post("/code-string", response_model=ListOfFunctions)
async def find_functions_on_script(req: Content):
    rc = RefactoringController(repo=os.getenv("REPO"))
    return {"functions": rc.find_functions_in_script(req.content)}


@list_route.get("/notebook", response_model=ListOfFunctions)
async def find_functions_on_notebook(path: str = Query(..., description="The Repos notebook path")):
    rc = RefactoringController(repo=os.getenv("REPO"))
    # algo
    # 1. export to a staging file
    # 2. perform find functions on script
    # 3. delete staging file
    return {"functions": rc.find_functions_on_notebook(path)}


@list_route.get("/file", response_model=ListOfFunctions)
async def find_functions_on_file(path: str = Query(..., description="The Repos Workspace Files path")):
    rc = RefactoringController(repo=os.getenv("REPO"))
    # algo
    # 1. convert path to wsfs path
    # 2. perform find functions on script
    return {"functions": rc.find_functions_on_file(path)}


# refactor functions
refactor_route = APIRouter()


class MoveRequest(BaseModel):
    src_path: str = Field(..., description="The source Repos path where the functions are located.")
    function_names: conlist(str, min_items=1) = Field(..., description="The array of function or class names.")
    dest_path: str = Field(..., description="The destination Repos path where the functions will be moved.")


@refactor_route.post("/move-functions")
async def move_functions(req: MoveRequest):
    rc = RefactoringController(repo=os.getenv("REPO"))
    rc.refactor(rc.ref_util.move_functions, req.src_path, req.function_names, req.dest_path)
    return f"moved {req.function_names} from {req.src_path} to {req.dest_path}"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(list_route, prefix="/list-functions")
app.include_router(refactor_route, prefix="/refactor")


@app.get("/")
async def root():
    return {"message": "Hello World"}
