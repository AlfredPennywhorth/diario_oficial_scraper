import sys
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 1. Garantir que o root do projeto correto esteja no início de sys.path de forma dinâmica
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
else:
    sys.path.remove(project_root)
    sys.path.insert(0, project_root)

# Não removemos mais caminhos dinamicamente a menos que sejam de fato inválidos,
# para evitar quebrar a execução na unidade D: do ambiente atual.
