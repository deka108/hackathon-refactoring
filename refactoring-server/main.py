import os

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from pydantic import BaseModel, conlist
from typing import List

from refactoring_utils import RefactoringUtils

root_path = Path('..').resolve()

ru = RefactoringUtils(root = str(root_path))

# listing functions
list_route = APIRouter()


class Content(BaseModel):
    content: str


class ListOfFunctions(BaseModel):
    functions: List[str]

    
@list_route.post("/code-string", response_model=ListOfFunctions)
async def find_functions_on_script(content: Content):
    return {"functions": ru.find_functions_on_script(content)}


@list_route.get("/notebook", response_model=ListOfFunctions)
async def find_functions_on_notebook(path: str):
    return {"functions": ru.find_functions_on_script(path)}


@list_route.get("/file", response_model=ListOfFunctions)
async def find_functions_on_file(path: str):
    return {"functions": ru.find_functions_on_script(path)}

# refactor functions
refactor_route = APIRouter()

class MoveRequest(BaseModel):
    src: str
    function_names: conlist(str, min_items=1)
    dst: str

@refactor_route.post("/move")
async def move(req: MoveRequest):
    mu.move_functions(req.src, req.function_names, req.dst)
    return f"moved {req.function_names} from {req.src} to {req.dst}"


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
