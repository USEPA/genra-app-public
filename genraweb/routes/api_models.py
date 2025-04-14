"""Models for API definitions."""
from enum import StrEnum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer

from genraweb.defs import EXTRA_FP_IDS, FILTER
from genraweb.lib.chem_id import UNNAMED
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.state import GenRAFlag


class CaseEnum(StrEnum):
    """Preserve uppercase characters for the values in the enum."""

    def _generate_next_value_(name, start, count, last_values):
        return name


## Fields ##

FPIDs = CaseEnum("FPIDs", [*list(FPGen.FPClass), *EXTRA_FP_IDS])
FILTERS = StrEnum("FILTERS", list(FILTER))
ENGINES = StrEnum("ENGINES", ["genrapred", "genrapy"])
FILE_TYPES = StrEnum("FILE_TYPES", ["html", "svg", "json"])

ChemID = Annotated[
    str,
    Field(
        description="GenRA chemical ID, DSSTOX SID or "
        "CID, CASRN, SMILES, preferred name.",
        # FIXME Pydantic docs. show `examples=list`, but that fails?
        example="DTXCID30182",
    ),
]
# High max. as some clients (program offices) looking for long lists.
MaxNeighbors = Annotated[
    int, Field(description="Maximum neighbors to return.", default=10, gt=0, le=5000)
]
Similarity = Annotated[
    float, Field(description="The similarity of two chemicals, 0-1.")
]
MinSimilarity = Annotated[
    Similarity,
    Field(
        default=0.1, description="Minimum similarity to accept when listing neighbors."
    ),
]
# FP ID needs to be plain str for comma separated lists (hybrids)
FPID = Annotated[FPIDs | str, Field(description="The FingerPrint IDendtifier.")]
FPWeights = Annotated[
    Optional[str],
    Field(
        default=None,
        description="Comma separated list of floating point weights "
        "for hybrid fingerprints.",
    ),
]
FilterBy = Annotated[
    Optional[FILTERS],
    Field(
        default="tox_txrf",
        description="Filter nearest neighbor results by this list of chemicals.",
    ),
]
Summarise = Annotated[str, Field(description="Summarization group", default="tox_txrf")]
SummariseBy = Annotated[str, Field(description="Summarization by", default="tox_fp")]


ChemicalName = Annotated[
    str, Field(description="The common name of the chemical.", default=UNNAMED)
]
SelectedChem = Annotated[
    bool, Field(description="True if this chemical is a selected (target) chemical.")
]
DTXSID = Annotated[str, Field(description="A DSSTox DB Substance IDentifier.")]
DTXCID = Annotated[str, Field(description="A DSSTox DB Compound IDentifier.")]
MolMass = Annotated[float, Field(description="The molecular mass of the chemical.")]
SimilarityTag = Annotated[
    str,
    Field(
        description="A prefix used in the UI to "
        "distinquish chemical, biological, and toxicological fingerprints."
    ),
]
CCDLink = Annotated[
    str,
    Field(description="A link for this chemical to the Comptox Chemicals Dashboard."),
]
Pos0 = Annotated[
    int,
    Field(
        description="The number positives for each toxicity classification.", default=1
    ),
]
Neg0 = Annotated[
    int,
    Field(
        description="The number negatives for each toxicity classification.", default=1
    ),
]
Engine = Annotated[
    ENGINES, Field(description="The prediction engine to use.", default="genrapred")
]
FileType = Annotated[
    FILE_TYPES, Field(description="File type for plot.", default="svg")
]
SearchText = Annotated[
    str,
    Field(
        description=(
            "A partial pattern containing chemical name, casrn, synonym, "
            "dtx sid, dtx cid. sid/cid should start with DTXSID/DTXCID."
        )
    ),
]
MinPositive = Annotated[
    int,
    Field(
        description="Minimum positive observations to make a positive prediction.",
        default=0,
    ),
]
MinNegative = Annotated[
    int,
    Field(
        description="Minimum negative observations to make a positive prediction.",
        default=0,
    ),
]
GraphSteps = Annotated[
    int,
    Field(
        description="The number of steps from the target to take when building answer.",
        default=3,
    ),
]
GraphType = Annotated[
    StrEnum("GRAPH_TYPES", ["all_nhgbrs", "out_only"]),
    Field(description="Type of links to return.", default="all_nhgbrs"),
]
GraphExpanded = Annotated[
    Optional[str],
    Field(
        description="Comma separated list of chem_ids expanded in view.", default=None
    ),
]
TableFileType = Annotated[
    CaseEnum("TABLE_FILE_TYPES", ["xlsx", "csv", "allNN", "RAview"]),
    Field(description="File type for table."),
]
GenFPChemIDs = Annotated[
    str,
    Field(
        description="List of chem_ids to run generation for. If 'MISSING', will run "
        "on detected candidates. If 'ALL', will run on all from scratch.",
        example="DTXCID30182",
        default="",
    ),
]
FPOrNN = Annotated[
    StrEnum("FP_OR_NN", ["fps", "nn"]),
    Field(description="Generate FPs or nearest neighbor counts.", default="fps"),
]
Stop = Annotated[
    StrEnum("ACTIONS", ["stop"]), Field(description="Action to take.", default="stop")
]
CollectionName = Annotated[
    Optional[str], Field(description="Name of DB collection.", default=None)
]
NumFiles = Annotated[
    int,
    Field(description="Number of most recently modified files to output.", default=5),
]
PredEngines = Annotated[list[dict], Field()]
SortOptions = Annotated[list[dict], Field()]
ReturnedData = Annotated[
    Optional[list[dict]], Field(description="A list of rows of data.", default=None)
]

HybridFPMax = Annotated[
    int, Field(description="Maximum number of fingerprints to hybridize.", default=3)
]

NeighborDataExists = Annotated[
    bool, Field(description="True if there is neighbor information for this FP.")
]

FPName = Annotated[str, Field(description="The descriptive name of the fingerprint.")]

FPDescription = Annotated[str, Field(description="Description of the fingerprint.")]

# Pydantic 3.x may have better support for Enum serialization, for now:


def read_flag_as_text(v):
    """Accept flag as text or integer."""
    try:
        v = int(v)
        return GenRAFlag(v)
    except ValueError:
        try:
            flag = GenRAFlag(0)
            for f in v.split("|"):
                flag |= GenRAFlag[f.upper()]
            return flag
        except KeyError:
            raise ValueError(f"Invalid flag value: {v}")


def write_flag_as_text(v):
    """Accept flag as text or integer.

    Flag Enums report their name as "Flag1|Flag4|Flag9".
    """
    return GenRAFlag(v).name


GenRAFlagEnum = Annotated[
    GenRAFlag,
    Field(
        description="Flags for GenRA prediction, pipe separated, "
        "e.g. 'USERNN' or 'USERNN|MULTITARGET'.  Possible values: "
        + ", ".join(f"'{f.name}'" for f in GenRAFlag),
    ),
    PlainSerializer(write_flag_as_text, return_type=str),
    BeforeValidator(read_flag_as_text),
]


## UI Endpoints ##


class NeighborBy(BaseModel):
    """FPs for which there is neighbor information."""

    key: FPIDs
    name: FPName
    description: FPDescription
    data_exists: NeighborDataExists


class FilterByItem(BaseModel):
    """Filters for the neighbor list."""

    key: FilterBy
    name: Annotated[str, Field(description="Name of the filter.")]
    description: Annotated[str, Field(description="Description of the filter.")]
    data_exists: Annotated[
        bool, Field(description="True if there is data for this filter.")
    ]


class HelpText(BaseModel):
    """Help text for the UI."""

    helpPosition: Annotated[str, Field(description="Position of the help text.")]
    iconType: Annotated[str, Field(description="Type of icon to use.")]
    helpTextId: Annotated[str, Field(description="ID of the help text.")]
    helpText: Annotated[str, Field(description="The help text, may include HTML.")]


class GraphTypeResponse(BaseModel):
    """Type of graphs to display in NN explorer."""

    data_exists: Annotated[
        bool, Field(description="True if there is data for this graph.")
    ]
    name: Annotated[str, Field(description="Name of the graph type.")]
    description: Annotated[str, Field(description="Description of the graph type.")]
    key: Annotated[str, Field(description="Key for the graph type.")]


class Download(BaseModel):
    """Download options for the UI."""

    subdir: Annotated[
        None | Literal["/csv", "/xlsx", "/allNN", "/RAview"],  # FIXME
        Field(description="Indicates subtype"),
    ]
    name: Annotated[str, Field(description="Name of the download option.")]
    description: Annotated[
        str, Field(description="Description of the download option.")
    ]
    data_exists: Annotated[bool, Field(description="True if there is data for this.")]
    rel: Annotated[
        Literal["/step/readacross/download", "/step/radial/download"],
        Field(description="Rel(ation) to the page."),
    ]


class Setup(BaseModel):
    """Get information to populate drop-downs, etc."""

    chem_id: ChemID


class SetupResponse(BaseModel, use_enum_values=True):
    """Information to populate drop-downs, etc."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[ChemicalName] = UNNAMED
    dsstox_sid: Optional[DTXSID] = Field(None)
    dsstox_cid: Optional[DTXCID] = Field(None)
    mol_weight: Optional[MolMass] = Field(None)
    smiles: Optional[str] = Field(None)
    is_markush: Optional[bool] = Field(None)
    casrn: Optional[str] = Field(None)
    chem_id: ChemID
    neighbor_by: list[NeighborBy]
    hybrid_fp_max: HybridFPMax
    fp_needs_gen: Annotated[
        list[FPIDs], Field(description="FP IDs for FPs that will require calculation.")
    ]
    help_text: list[HelpText]
    filter_by: list[FilterByItem]
    graph_type: list[GraphTypeResponse]
    fpColor: Annotated[
        dict[FPIDs, str],
        Field(description="CSS color for each FP in NN explorer view."),
    ]
    initGraphFPs: Annotated[
        list[FPIDs], Field(description="Initial FPs to display in NN explorer view.")
    ]
    download: list[Download]
    error_msg: Optional[str] = Field(
        description="Error message explaining why chemical can't be processed.",
        default=None,
    )
    flags: Optional[GenRAFlagEnum] = None

class BaseItem(BaseModel):
    """Common fields for an item returned by GenRA API responses."""

    data_exists: bool
    description: str
    key: str
    name: str

class RadialView(BaseModel):
    """Nearest neighbor list with similarities, for GenRA's radial plot."""

    chem_id: ChemID
    k0: MaxNeighbors
    s0: MinSimilarity
    fp: FPID
    fp_weight: FPWeights
    sel_by: FilterBy


class RadialViewResponseItem(BaseModel):
    """Nearest neighbor entry, for GenRA's radial plot."""

    name: ChemicalName
    chem_id: ChemID
    selected: SelectedChem
    dtxsid: Optional[DTXSID] = None # input chemical may not have IDs
    dtxcid: Optional[DTXCID] = None
    weight: Optional[MolMass] = None
    value: Similarity
    similarity_tag: SimilarityTag
    details_link: Optional[CCDLink] = None


class RadialViewReportDbResponseItem(BaseItem):
    """Database info returned by RadialView endpoint."""

    subFields: list[BaseItem]


class RadialViewResponse(BaseModel):
    """A radial layout of chemical hits."""

    result: list[RadialViewResponseItem]
    report_db: list[RadialViewReportDbResponseItem]
    sel_by: FilterBy
    flags: Optional[GenRAFlagEnum] = None


class PhyschemPlot(RadialView):
    """Generate plot for physchem properties of neighborhood."""

    ftype: FileType


class FingerPrintHeatChart(RadialView):
    """Render summary of ct,bio,tox information for chemical."""

    chem_id: ChemID
    k0: MaxNeighbors = 100
    fp: FPID
    fp_weight: FPWeights
    sel_by: FilterBy


class FingerPrintHeatChartColumn(BaseModel):
    """Metadata for each column in the heat map."""

    headerName: str
    headerTooltip: str
    field: str
    tooltipField: str
    cellRenderer: str
    cellRendererParams: dict
    suppressHeaderMenuButton: bool
    lockPosition: str
    filter: bool
    minWidth: Optional[int] = Field(None)
    cellClass: str
    hide: bool


class FingerPrintHeatChartData(BaseModel):
    """Data for each row in the heat map."""

    chem_id: ChemID
    dtxcid: DTXCID
    dtxsid: DTXSID
    name: ChemicalName
    details_link: CCDLink


class FingerPrintHeatChartResponse(BaseModel):
    """A visual summary of bio/tox for neighbouring chemicals."""

    columns: list[FingerPrintHeatChartColumn]
    data: ReturnedData


class ReadAcrossColumn(BaseModel):
    """Metadata for each column in the read across table."""

    cellStyle: Optional[dict] = Field(None)
    colId: Optional[str] = Field(None)
    field: str
    filter: Optional[str] = Field(None)
    floatingFilter: Optional[bool] = Field(None)
    headerComponentParams: dict
    headerName: str
    headerTooltip: str
    hide: Optional[bool] = Field(None)
    minWidth: Optional[int] = Field(None)
    maxWidth: Optional[int] = Field(None)
    suppressColumnsToolPanel: bool
    tooltipField: str
    suppressHeaderMenuButton: Optional[bool] = Field(None)
    sortable: Optional[bool] = Field(None)


class GenerateReadAcrossResponse(BaseModel):
    """Show information for target and neighbors."""

    predEngines: PredEngines
    sortOptions: SortOptions
    columns: Optional[list[ReadAcrossColumn]] = Field(None)
    data: ReturnedData


class GenerateReadAcross(RadialView):
    """Show information for target and neighbors."""

    summarise: Summarise
    sumrs_by: SummariseBy
    flags: str = Field("")


class uiRunReadAcross(GenerateReadAcross):
    """Run GenRA prediction and analysis for UI."""

    chem_inc: list[dict]  # list of dict, chem_id and isChecked
    tox_inc: Optional[list[str]] = Field(None)
    pos0: Pos0
    neg0: Neg0
    useWidth: bool = False
    s0: MinSimilarity = 0.01
    k0: MaxNeighbors = 12
    engine: Engine = "genrapy"


class uiRunReadAcrossResponse(BaseModel):
    """Predictions of effect based on neighbors."""

    sortOptions: SortOptions
    columns: Optional[list[ReadAcrossColumn]] = Field(None)
    data: ReturnedData


class AssayList(GenerateReadAcross):
    """Data summary table, for GenRA's data availability panel."""

    columns: Optional[list[dict]] = Field(None)
    data: ReturnedData


class AssayListResponse(BaseModel):
    """A summary of bio/tox for neighbouring chemicals."""

    # cellRenderer: Optional[dict] # unsure of type
    cellStyle: Optional[dict] = Field(None)
    colId: Optional[str] = Field(None)
    field: str
    filter: Optional[str] = Field(None)
    floatingFilter: Optional[bool] = Field(None)
    headerComponentParams: dict
    headerName: str
    headerTooltip: str
    hide: Optional[bool] = Field(None)
    minWidth: Optional[int] = Field(None)
    maxWidth: Optional[int] = Field(None)
    suppressColumnsToolPanel: bool
    tooltipField: str
    suppressHeaderMenuButton: Optional[bool] = Field(None)
    sortable: Optional[bool] = Field(None)


class FastNN(RadialView):
    """Nearest neighbors from fp_info if present."""

    steps: GraphSteps
    expanded: GraphExpanded
    graph_type: GraphType


class FastNNResponse(BaseModel):
    """Nearest Neighbor data."""

    edges: list[dict]
    nodes: dict[ChemID, dict]


class DownloadPath(BaseModel):
    """Download Genrate / Run read-across results."""

    ftype: TableFileType


class DownloadBody(uiRunReadAcross):
    """Details of tox for neighbouring chemicals."""

    chem_inc: Optional[list[dict]] = Field(None)
    pos0: Pos0 = 0
    neg0: Neg0 = 0
    rra: bool = False


## Domain Endpoints ##


class ChemNN(RadialView):
    """Get nearest neighbors for chem. with FP."""

    pass


class DataMatrix(GenerateReadAcross):
    """Get tox information for chemical nearest neighbours for RA."""

    s0: MinSimilarity = 0.01
    k0: MaxNeighbors = 12


class DomainResponse(BaseModel):
    """Response from a GenRA science domain endpoint."""

    coldef: list[dict]
    rowdef: list[dict]
    row: list[dict]


class RunReadAcross(DataMatrix):
    """Run GenRA prediction and analysis."""

    minpos: MinPositive
    minneg: MinNegative
    engine: Engine
    useWidth: bool = False


class DataAvailability(DataMatrix):
    """Summarize data availability for a given chemical."""

    dsstox_cid: Optional[DTXCID] = Field(None)


## Default Endpoints ##
# TODO: add more tags (admin?)


class BuildInfo(BaseModel):
    """An endpoint for various app build info - database, python version, etc."""

    num_files: NumFiles


class BuildInfoResponse(BaseModel):
    """Various app build info."""

    python_version: str
    mongodb: dict
    git_log: list[str]
    time_image_built: str
    time_app_start: str
    recent_files: list[dict]


class SearchChems(BaseModel):
    """Search chemicals."""

    txt: SearchText


class SearchChemsResult(BaseModel):
    """Chemical search result."""

    casrn: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    smiles: Optional[str] = Field(None)
    dsstox_cid: Optional[DTXCID] = Field(None)
    dsstox_sid: Optional[DTXSID] = Field(None)
    chem_id: str


class SearchChemsResponse(BaseModel):
    """Search Chemicals"""

    hits: list[SearchChemsResult]


class ManageCoverage(BaseModel):
    """An endpoint to commit coverage results to disk and HTML."""

    stop: Stop


class GenFP(BaseModel):
    """Generates all FP fingerprints for candidate chemicals."""

    chem_ids: GenFPChemIDs
    fp: FPID
    fp_or_nn: FPOrNN
    collection_name: CollectionName
    sel_by: FilterBy = "tox_txrf"


class ViewChemPath(BaseModel):
    """View the input chemical in svg format."""

    chem_id: ChemID


class HealthCheckResponse(BaseModel):
    """Status of DB and cache connections."""

    status: str
    generated: str
    db: dict
    cache: dict


class ClearCacheResponse(BaseModel):
    """Report of cleared keys."""

    keys_cleared: int
    match: str
    time: str
    keys: list[str]


class PhyschemJSONResponse(BaseModel):
    """JSON formatted representation of Physchem Plot."""

    data: list[dict]
    layout: dict
