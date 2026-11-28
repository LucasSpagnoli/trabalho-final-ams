# Expansão do Dicionário de Libras — AMS0002

Protótipo de API para cadastro, consulta e revisão de sinais da Libras, com variações regionais e vídeos. Trabalho final de Análise e Modelagem de Sistemas, UDESC. A interface interativa da própria API fica em `/docs` (Swagger); não há front-end.

## Tecnologias

Python 3.11+, FastAPI, Pydantic, SQLite, Uvicorn e armazenamento local de vídeos. O protótipo usa módulos simples e persistência SQLite; produção exigiria armazenamento privado, processamento de mídia, autenticação de contas, infraestrutura e auditoria mais completos.

## Como executar

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:AMS_ADMIN_KEY = "troque-por-chave-longa-de-admin"
$env:AMS_COLLABORATOR_KEY = "troque-por-chave-longa-de-colaborador"
uvicorn app:app --reload
```

No Linux/macOS, ative o ambiente com `source .venv/bin/activate` e configure as variáveis com `export`. Abra http://127.0.0.1:8000/docs. Envie `X-API-Key` no cabeçalho das operações de escrita; opcionalmente envie `X-User` para identificar o autor na auditoria. Use chaves diferentes e não as publique no Git. `AMS_DATA_DIR` permite configurar a pasta do banco e dos vídeos (padrão `.data`). Os dados persistem entre reinicializações.

## Fluxo e endpoints

| Operação | Rota | Acesso |
| --- | --- | --- |
| Cadastrar sinal com campos descritivos e gramaticais | `POST /sinais` | Colaborador ou Administrador |
| Buscar por palavra, acepção, exemplo, assunto ou número; filtrar e ordenar | `GET /sinais` | Público Geral |
| Consultar sinal e variações aprovadas | `GET /sinais/{id}` | Público Geral |
| Alterar campos individualmente, inclusive limpar opcionais com `null`; excluir sinal | `PATCH/DELETE /sinais/{id}` | Administrador |
| Enviar variação regional e vídeos do sinal e do exemplo | `POST /sinais/{id}/variacoes` | Colaborador ou Administrador |
| Alterar região ou excluir variação | `PATCH/DELETE /variacoes/{id}` | Administrador |
| Revogar consentimento e retirar vídeos | `POST /variacoes/{id}/revogar-consentimento` | Autor da variação ou Administrador |
| Consultar vídeo | `GET /videos/{id}` | Público se aprovado; Administrador se pendente |
| Consultar fila | `GET /revisao` | Administrador |
| Aprovar ou recusar | `POST /revisao/sinais/{id}`, `POST /revisao/variacoes/{id}` | Administrador |

O cadastro do Administrador entra como **Aprovado**; o do Colaborador entra como **Submetido**. Só o Administrador muda o estado para **Aprovado** ou **Recusado**. O catálogo público só mostra sinais e variações aprovados. Uma variação enviada por Colaborador para sinal aprovado precisa de aprovação própria.

O JSON de sinal inclui `palavra` e `descricao_textual` obrigatórias; campos opcionais: `numero`, `assunto`, `acepcao`, `exemplo`, `exemplo_libras`, `classe_gramatical`, `origem`, `mao`, `imagem`, `ponto_articulacao`, `configuracao_mao`, `disposicao_mao`, `orientacao_mao`, `regiao_contato`, `componentes_nao_manuais`, `classificacao`. O upload é `multipart/form-data` com `regiao`, `consentiu=true`, `termo_versao`, `maior_de_18=true`, `video` e, opcionalmente, `video_exemplo`. Apenas MP4 e WebM de até 40 MiB por arquivo são aceitos. O registro guarda versão, instante e identificador do aceite. Menores são bloqueados até existir um fluxo verificável de autorização do responsável. O vídeo do exemplo pode ser consultado com `GET /videos/{id}?tipo=exemplo`. Ao recusar ou revogar, elimina os vídeos associados.

### Exemplo rápido

```powershell
$headers = @{ "X-API-Key" = $env:AMS_COLLABORATOR_KEY; "X-User" = "lucas" }
Invoke-RestMethod http://127.0.0.1:8000/sinais -Method Post -Headers $headers -ContentType 'application/json' -Body '{"palavra":"AMIGO","assunto":"Pessoas","descricao_textual":"Descrição do movimento e da configuração de mão."}'
```

Use o identificador retornado no formulário de `POST /sinais/{id}/variacoes` no Swagger. O Administrador consulta `/revisao` e envia, por exemplo, `{"decisao":"Aprovado"}` para as rotas de revisão. Para testar os fluxos automaticamente após instalar as dependências, execute `python -m unittest discover -s tests -v`.

## Limites do protótipo

O aceite registrado no upload é uma demonstração técnica: não verifica a identidade do sinalizante; menores são rejeitados. Não use vídeos de pessoas reais sem autorização válida. Não há remoção de metadados, processamento de vídeo, expiração automática de dados, miniaturas, serviço de e-mail, testes de desempenho/WCAG ou implantação com TLS. Estas partes pertencem à proposta de modelagem e exigem implementação antes de uso público. As chaves de API são compartilhadas por perfil e servem apenas para demonstração local.

## Integrantes e atividades

| Integrante | Atividades |
| --- | --- |
| Luana Medeiros | Perfis, histórias de usuário, requisitos funcionais e não funcionais, diagrama de atividades. |
| Higor Moreira | WCAG, LGPD, caso de uso estruturado e proposta arquitetural. |
| Kailani Maffei | Diagrama de classes, diagrama de sequência e consolidação do documento e apresentação. |
| Lucas Spagnoli | Protótipo da API, repositório e README. |

## Referências do trabalho

O enunciado solicita CRUD de todos os campos, variações linguísticas, parâmetros da gramática da Libras e vídeo do sinal e do exemplo em Libras. O modelo de dados contempla `exemplo_libras` descritivo e o vídeo opcional do exemplo na variação.
