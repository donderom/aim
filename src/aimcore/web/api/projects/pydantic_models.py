from pydantic import BaseModel
from typing import Dict, List, Optional, Union


class ProjectApiOut(BaseModel):
    name: str
    path: str
    description: str
    telemetry_enabled: int


class ProjectParamsOut(BaseModel):
    params: Optional[Dict] = None
    metric: Optional[Dict[str, list]] = None
    images: Optional[Dict[str, list]] = None
    texts: Optional[Dict[str, list]] = None
    figures: Optional[Dict[str, list]] = None
    distributions: Optional[Dict[str, list]] = None
    audios: Optional[Dict[str, list]] = None
    figures3d: Optional[Dict[str, list]] = None


class ProjectActivityApiOut(BaseModel):
    num_experiments: int
    num_runs: int
    num_archived_runs: int
    num_active_runs: int
    activity_map: Dict[str, int] = {"2021-01-01": 54}


class Sequence(BaseModel):
    name: str
    context: dict


class ProjectPinnedSequencesApiOut(BaseModel):
    sequences: List[Sequence] = []


class ProjectPinnedSequencesApiIn(BaseModel):
    sequences: List[Sequence]


class PackageRegisteredModels(BaseModel):
    sequences: List[str]
    containers: List[str]
    functions: List[str]


ProjectNamesList = List[str]
ProjectPackageRegisteredModels = Dict[str, PackageRegisteredModels]
ProjectPackagesApiOut = Union[ProjectNamesList, ProjectPackageRegisteredModels]
