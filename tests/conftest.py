"""Marca os módulos de raio_x como carregados agora: o recarregamento do app.py (_recarregar_raio_x) só age
quando um arquivo muda, e não troca as classes de erro que os testes já importaram."""
import os
import sys

import raio_x.das, raio_x.entrada, raio_x.explicacao, raio_x.lacunas, raio_x.modelo, raio_x.nfse  # noqa: E401,F401
import raio_x.painel, raio_x.receita  # noqa: E401,F401

for _nome, _m in list(sys.modules.items()):
    if _nome.startswith("raio_x.") and getattr(_m, "__file__", None):
        _m._mtime_raiox = os.path.getmtime(_m.__file__)
