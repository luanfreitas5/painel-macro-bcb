"""Ingestão de dados do Banco Central (camada bronze).

Módulos
-------
cache
    Snapshots datados em Parquet + manifesto com hash; reuso idempotente por TTL.
retry
    Chamada com novas tentativas para falhas transitórias de rede.
sgs
    Coleta de séries do SGS por janelas de data.
focus
    Coleta das expectativas mensais do Focus (OData/Olinda).
"""
