"""Protótipo do dicionário de Libras. Execute com uvicorn app:app --reload."""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(os.getenv("AMS_DATA_DIR", ".data"))
ROOT.mkdir(parents=True, exist_ok=True)
MEDIA = ROOT / "media"
MEDIA.mkdir(exist_ok=True)
DB = ROOT / "ams.sqlite3"
MAX_VIDEO = 40 * 1024 * 1024
FIELDS = {"numero", "assunto", "palavra", "acepcao", "exemplo", "exemplo_libras", "classe_gramatical", "origem", "mao", "imagem", "ponto_articulacao", "configuracao_mao", "disposicao_mao", "orientacao_mao", "regiao_contato", "componentes_nao_manuais", "classificacao", "descricao_textual"}
app = FastAPI(title="Dicionário de Libras — AMS", version="1.0.0")


@contextmanager
def connection():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


with connection() as db:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS sinais (id INTEGER PRIMARY KEY, dados TEXT NOT NULL, status TEXT NOT NULL, autor TEXT NOT NULL, criado_em TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS variacoes (id INTEGER PRIMARY KEY, sinal_id INTEGER NOT NULL REFERENCES sinais(id) ON DELETE CASCADE, regiao TEXT NOT NULL, status TEXT NOT NULL, video TEXT, consentimento TEXT);
    CREATE TABLE IF NOT EXISTS auditoria (id INTEGER PRIMARY KEY, entidade TEXT NOT NULL, entidade_id INTEGER NOT NULL, acao TEXT NOT NULL, ator TEXT NOT NULL, instante TEXT NOT NULL);
    """)
    columns = {r[1] for r in db.execute("PRAGMA table_info(variacoes)")}
    if "video_exemplo" not in columns:
        db.execute("ALTER TABLE variacoes ADD COLUMN video_exemplo TEXT")
    if "autor" not in columns:
        db.execute("ALTER TABLE variacoes ADD COLUMN autor TEXT")


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(x_api_key: str | None = Header(None), x_user: str | None = Header(None)):
    if x_api_key and os.getenv("AMS_ADMIN_KEY") and x_api_key == os.getenv("AMS_ADMIN_KEY"):
        return "Administrador", (x_user or "administrador")
    if x_api_key and os.getenv("AMS_COLLABORATOR_KEY") and x_api_key == os.getenv("AMS_COLLABORATOR_KEY"):
        return "Colaborador", (x_user or "colaborador")
    raise HTTPException(401, "Chave inválida ou ausente")


def admin(user=Depends(identity)):
    if user[0] != "Administrador":
        raise HTTPException(403, "Apenas Administrador")
    return user


def audit(db, entity, entity_id, action, user):
    db.execute("INSERT INTO auditoria(entidade,entidade_id,acao,ator,instante) VALUES (?,?,?,?,?)", (entity, entity_id, action, user, now()))


class Signal(BaseModel):
    numero: int | None = None
    assunto: str | None = None
    palavra: str = Field(min_length=1)
    acepcao: str | None = None
    exemplo: str | None = None
    exemplo_libras: str | None = None
    classe_gramatical: str | None = None
    origem: str | None = None
    mao: str | None = None
    imagem: str | None = None
    ponto_articulacao: str | None = None
    configuracao_mao: str | None = None
    disposicao_mao: str | None = None
    orientacao_mao: str | None = None
    regiao_contato: str | None = None
    componentes_nao_manuais: str | None = None
    classificacao: str | None = None
    descricao_textual: str = Field(min_length=1)


def get_signal(db, id):
    row = db.execute("SELECT * FROM sinais WHERE id=?", (id,)).fetchone()
    if not row:
        raise HTTPException(404, "Sinal não encontrado")
    return row


def serialize(db, row, public=False):
    variations = db.execute("SELECT * FROM variacoes WHERE sinal_id=?", (row["id"],)).fetchall()
    return {"id": row["id"], **json.loads(row["dados"]), "status": row["status"], "variacoes": [{"id": v["id"], "regiao": v["regiao"], "status": v["status"], "video_url": f"/videos/{v['id']}" if v["video"] else None, "video_exemplo_url": f"/videos/{v['id']}?tipo=exemplo" if v["video_exemplo"] else None} for v in variations if not public or v["status"] == "Aprovado"]}


@app.post("/sinais", status_code=201)
def create_signal(payload: Signal, user=Depends(identity)):
    with connection() as db:
        status = "Aprovado" if user[0] == "Administrador" else "Submetido"
        cur = db.execute("INSERT INTO sinais(dados,status,autor,criado_em) VALUES (?,?,?,?)", (payload.model_dump_json(), status, user[1], now()))
        audit(db, "sinal", cur.lastrowid, status, user[1])
        return serialize(db, get_signal(db, cur.lastrowid))


@app.get("/sinais")
def list_signals(q: str | None = None, assunto: str | None = None, mao: str | None = None, ordenar: str = Query("alfabetica", pattern="^(alfabetica|assunto|numero)$")):
    with connection() as db:
        rows = [serialize(db, r, public=True) for r in db.execute("SELECT * FROM sinais WHERE status='Aprovado'")]
    if q:
        rows = [r for r in rows if any(q.casefold() in str(r.get(k) or "").casefold() for k in ("palavra", "acepcao", "exemplo", "assunto", "numero"))]
    if assunto:
        rows = [r for r in rows if (r.get("assunto") or "").casefold() == assunto.casefold()]
    if mao:
        rows = [r for r in rows if (r.get("mao") or "").casefold() == mao.casefold()]
    rows.sort(key=lambda r: (r.get("numero") or 0) if ordenar == "numero" else (r.get("assunto") or "").casefold() if ordenar == "assunto" else r["palavra"].casefold())
    return rows


@app.get("/sinais/{sinal_id}")
def read_signal(sinal_id: int):
    with connection() as db:
        row = get_signal(db, sinal_id)
        if row["status"] != "Aprovado":
            raise HTTPException(404, "Sinal não encontrado")
        return serialize(db, row, public=True)


@app.patch("/sinais/{sinal_id}")
def update_signal(sinal_id: int, fields: dict, user=Depends(admin)):
    if set(fields) - FIELDS or "palavra" in fields and not fields["palavra"] or "descricao_textual" in fields and not fields["descricao_textual"]:
        raise HTTPException(422, "Campo desconhecido ou obrigatório vazio")
    with connection() as db:
        row = get_signal(db, sinal_id)
        data = json.loads(row["dados"])
        data.update(fields)
        Signal.model_validate(data)
        db.execute("UPDATE sinais SET dados=? WHERE id=?", (json.dumps(data, ensure_ascii=False), sinal_id))
        audit(db, "sinal", sinal_id, "alterado", user[1])
        return serialize(db, get_signal(db, sinal_id))


@app.delete("/sinais/{sinal_id}", status_code=204)
def delete_signal(sinal_id: int, user=Depends(admin)):
    with connection() as db:
        get_signal(db, sinal_id)
        for row in db.execute("SELECT video,video_exemplo FROM variacoes WHERE sinal_id=?", (sinal_id,)):
            for filename in (row["video"], row["video_exemplo"]):
                if filename:
                    (MEDIA / filename).unlink(missing_ok=True)
        db.execute("DELETE FROM sinais WHERE id=?", (sinal_id,))
        audit(db, "sinal", sinal_id, "excluido", user[1])


@app.post("/sinais/{sinal_id}/variacoes", status_code=201)
async def create_variation(sinal_id: int, regiao: str = Form(...), consentiu: bool = Form(...), termo_versao: str = Form(...), maior_de_18: bool = Form(...), video: UploadFile = File(...), video_exemplo: UploadFile | None = File(None), user=Depends(identity)):
    if not regiao.strip() or not consentiu or not termo_versao.strip():
        raise HTTPException(422, "Região e consentimento são obrigatórios")
    if not maior_de_18:
        raise HTTPException(422, "Vídeos de menores exigem confirmação do responsável; indisponível neste protótipo")
    with connection() as db:
        signal = get_signal(db, sinal_id)
        if user[0] != "Administrador" and signal["status"] != "Aprovado" and signal["autor"] != user[1]:
            raise HTTPException(403, "Sem acesso ao sinal")
        saved = []
        try:
            filename = await save_video(video)
            saved.append(filename)
            example_name = await save_video(video_exemplo) if video_exemplo is not None else None
            if example_name:
                saved.append(example_name)
            status = "Aprovado" if user[0] == "Administrador" else "Submetido"
            consent = json.dumps({"versao": termo_versao, "instante": now(), "responsavel": user[1]})
            cur = db.execute("INSERT INTO variacoes(sinal_id,regiao,status,video,consentimento,video_exemplo,autor) VALUES (?,?,?,?,?,?,?)", (sinal_id, regiao.strip(), status, filename, consent, example_name, user[1]))
            audit(db, "variacao", cur.lastrowid, status, user[1])
        except Exception:
            for name in saved:
                (MEDIA / name).unlink(missing_ok=True)
            raise
        return {"id": cur.lastrowid, "status": status, "video_url": f"/videos/{cur.lastrowid}"}


async def save_video(video: UploadFile):
    extension = Path(video.filename or "").suffix.lower()
    if video.content_type not in ("video/mp4", "video/webm") or (extension, video.content_type) not in ((".mp4", "video/mp4"), (".webm", "video/webm")):
        raise HTTPException(422, "Envie um vídeo MP4 ou WebM")
    filename = uuid.uuid4().hex + extension
    path = MEDIA / filename
    total = 0
    try:
        with path.open("wb") as target:
            while chunk := await video.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_VIDEO:
                    raise HTTPException(413, "O vídeo deve ter até 40 MB")
                target.write(chunk)
        with path.open("rb") as source:
            header = source.read(16)
        if not (header[4:8] == b"ftyp" if extension == ".mp4" else header.startswith(b"\x1a\x45\xdf\xa3")):
            raise HTTPException(422, "Conteúdo de vídeo inválido")
        return filename
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.get("/videos/{variacao_id}")
def get_video(variacao_id: int, tipo: str = Query("sinal", pattern="^(sinal|exemplo)$"), x_api_key: str | None = Header(None)):
    with connection() as db:
        row = db.execute("SELECT v.*,s.status AS sinal_status FROM variacoes v JOIN sinais s ON s.id=v.sinal_id WHERE v.id=?", (variacao_id,)).fetchone()
        filename = row["video" if tipo == "sinal" else "video_exemplo"] if row else None
        if not filename:
            raise HTTPException(404, "Vídeo não encontrado")
        if (row["status"], row["sinal_status"]) != ("Aprovado", "Aprovado") and not (x_api_key and os.getenv("AMS_ADMIN_KEY") and x_api_key == os.getenv("AMS_ADMIN_KEY")):
            raise HTTPException(404, "Vídeo não encontrado")
        path = MEDIA / filename
        return FileResponse(path, media_type="video/mp4" if path.suffix == ".mp4" else "video/webm")


@app.get("/revisao")
def queue(user=Depends(admin)):
    with connection() as db:
        return {"sinais": [serialize(db, r) for r in db.execute("SELECT * FROM sinais WHERE status='Submetido'")], "variacoes": [dict(r) for r in db.execute("SELECT id,sinal_id,regiao,status FROM variacoes WHERE status='Submetido'")]}


def review(db, table, id, decision, user):
    if decision not in ("Aprovado", "Recusado"):
        raise HTTPException(422, "Decisão deve ser Aprovado ou Recusado")
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone()
    if not row:
        raise HTTPException(404, "Registro não encontrado")
    if row["status"] != "Submetido":
        raise HTTPException(409, "Registro já revisado")
    db.execute(f"UPDATE {table} SET status=? WHERE id=? AND status='Submetido'", (decision, id))
    if decision == "Recusado" and table == "variacoes":
        for filename in (row["video"], row["video_exemplo"]):
            if filename:
                (MEDIA / filename).unlink(missing_ok=True)
        db.execute("UPDATE variacoes SET video=NULL,video_exemplo=NULL,consentimento=NULL WHERE id=?", (id,))
    audit(db, "sinal" if table == "sinais" else "variacao", id, decision, user[1])
    return {"id": id, "status": decision}


class Decision(BaseModel):
    decisao: str


@app.post("/revisao/sinais/{sinal_id}")
def review_signal(sinal_id: int, payload: Decision, user=Depends(admin)):
    with connection() as db:
        result = review(db, "sinais", sinal_id, payload.decisao, user)
        if payload.decisao == "Recusado":
            for v in db.execute("SELECT video,video_exemplo FROM variacoes WHERE sinal_id=?", (sinal_id,)):
                for filename in (v["video"], v["video_exemplo"]):
                    if filename:
                        (MEDIA / filename).unlink(missing_ok=True)
            db.execute("UPDATE variacoes SET video=NULL,video_exemplo=NULL,consentimento=NULL,status='Recusado' WHERE sinal_id=?", (sinal_id,))
        return result


@app.post("/revisao/variacoes/{variacao_id}")
def review_variation(variacao_id: int, payload: Decision, user=Depends(admin)):
    with connection() as db:
        return review(db, "variacoes", variacao_id, payload.decisao, user)


@app.patch("/variacoes/{variacao_id}")
def update_variation(variacao_id: int, regiao: str, user=Depends(admin)):
    if not regiao.strip():
        raise HTTPException(422, "Região obrigatória")
    with connection() as db:
        if not db.execute("SELECT id FROM variacoes WHERE id=?", (variacao_id,)).fetchone():
            raise HTTPException(404, "Variação não encontrada")
        db.execute("UPDATE variacoes SET regiao=? WHERE id=?", (regiao.strip(), variacao_id))
        audit(db, "variacao", variacao_id, "alterada", user[1])
        return {"id": variacao_id, "regiao": regiao.strip()}


@app.delete("/variacoes/{variacao_id}", status_code=204)
def delete_variation(variacao_id: int, user=Depends(admin)):
    with connection() as db:
        row = db.execute("SELECT * FROM variacoes WHERE id=?", (variacao_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Variação não encontrada")
        for filename in (row["video"], row["video_exemplo"]):
            if filename:
                (MEDIA / filename).unlink(missing_ok=True)
        db.execute("DELETE FROM variacoes WHERE id=?", (variacao_id,))
        audit(db, "variacao", variacao_id, "excluida", user[1])


@app.post("/variacoes/{variacao_id}/revogar-consentimento")
def revoke_consent(variacao_id: int, user=Depends(identity)):
    with connection() as db:
        row = db.execute("SELECT * FROM variacoes WHERE id=?", (variacao_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Variação não encontrada")
        if user[0] != "Administrador" and row["autor"] != user[1]:
            raise HTTPException(403, "Sem acesso à variação")
        for filename in (row["video"], row["video_exemplo"]):
            if filename:
                (MEDIA / filename).unlink(missing_ok=True)
        db.execute("UPDATE variacoes SET status='Recusado',video=NULL,video_exemplo=NULL,consentimento=NULL WHERE id=?", (variacao_id,))
        audit(db, "variacao", variacao_id, "consentimento revogado", user[1])
        return {"id": variacao_id, "status": "Recusado"}
