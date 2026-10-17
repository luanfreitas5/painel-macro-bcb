"""Transformações em Polars: bronze -> silver -> gold.

Módulos
-------
validation
    Contratos de dados (colunas, unicidade, faixas) nas fronteiras entre camadas.
silver
    Limpeza e tipagem das séries SGS e do Focus.
gold
    Painel mensal: alinhamento de frequências, variações e IPCA acumulado em 12 meses.
"""
