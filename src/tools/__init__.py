import logging

from .search import web_search, web_research
from .todo import write_todos
from .ls import list_directory
from .read_file import read_file
from .write_file import write_file
from .grep import search_file_content
from .edit import replace

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 屏蔽第三方库的冗余日志
logging.getLogger("primp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("ddgs").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
