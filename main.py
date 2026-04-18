import os
import io
import pandas as pd
from typing import Optional
from fastapi import FastAPI, Request, Depends, File, UploadFile, Cookie, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from mangum import Mangum
from jose import jwt, JWTError
from services.pdf_generator import GeneradorPDF
from fastapi.responses import Response

# --- IMPORTACIONES MODULARES ---
from core.database import engine, Base, get_db, SessionLocal
from models import db_models
from models.db_models import DBUsuario
from services.transactions import GestorTransacciones
from services.auth import verificar_password, obtener_password_hash, crear_token_acceso, SECRET_KEY, ALGORITHM

# Crear las tablas en la BD si no existen
db_models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Control Financiero Modular")
templates = Jinja2Templates(directory="templates")


# ==========================================
# 1. SEGURIDAD Y AUTENTICACIÓN
# ==========================================

# Dependencia Guardián: Verifica si el usuario tiene sesión activa
def obtener_usuario_actual(token: str = Cookie(None), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    except JWTError:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})

    user = db.query(DBUsuario).filter(DBUsuario.username == username).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


# Creador de Admin por defecto (Se ejecuta al arrancar el server)
@app.on_event("startup")
def crear_admin_inicial():
    db = SessionLocal()
    if not db.query(DBUsuario).first():
        admin = DBUsuario(username="admin", password_hash=obtener_password_hash("admin123"))
        db.add(admin)
        db.commit()
    db.close()


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request}
    )


@app.post("/login")
async def procesar_login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")

    user = db.query(DBUsuario).filter(DBUsuario.username == username).first()
    if not user or not verificar_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "error": "Usuario o contraseña incorrectos"}
        )

    # Creamos la sesión y la guardamos en una cookie segura
    token = crear_token_acceso(data={"sub": user.username})
    response = RedirectResponse(url="/", status_code=303)  # Redirigimos al dashboard al entrar
    response.set_cookie(key="token", value=token, httponly=True)
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("token")
    return response


# ==========================================
# 2. RUTAS DE ADMINISTRACIÓN
# ==========================================

@app.get("/admin", response_class=HTMLResponse)
def panel_admin(request: Request, mensaje: str = None, error: str = None, db: Session = Depends(get_db),
                current_user: DBUsuario = Depends(obtener_usuario_actual)):
    usuarios = db.query(DBUsuario).all()
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request,
            "usuarios": usuarios,
            "usuario_actual": current_user,
            "mensaje": mensaje,
            "error": error
        }
    )


@app.post("/admin/usuarios")
async def crear_usuario(request: Request, db: Session = Depends(get_db),
                        current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form = await request.form()
    username = form.get("username").strip()
    password = form.get("password").strip()

    if db.query(DBUsuario).filter(DBUsuario.username == username).first():
        return RedirectResponse(url="/admin?error=El nombre de usuario ya existe", status_code=303)

    nuevo_user = DBUsuario(username=username, password_hash=obtener_password_hash(password))
    db.add(nuevo_user)
    db.commit()
    return RedirectResponse(url="/admin?mensaje=Usuario creado con éxito", status_code=303)


@app.get("/admin/exportar_db")
def exportar_base_datos(current_user: DBUsuario = Depends(obtener_usuario_actual)):
    # Reemplaza "finanzas.db" con el nombre real de tu archivo SQLite si es diferente
    file_path = "finanzas.db"

    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename="Backup_Finanzas_DB.db", media_type="application/octet-stream")
    return RedirectResponse(url="/admin?error=No se encontró el archivo de base de datos físico", status_code=303)


# ==========================================
# 3. RUTAS DE LECTURA (GET) PROTEGIDAS
# ==========================================

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, mensaje: str = None, error: str = None, db: Session = Depends(get_db),
              current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    resumen = tx.obtener_resumen_dashboard()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "contratos": resumen,
            "mensaje": mensaje,
            "error": error,
            "usuario_actual": current_user
        }
    )


@app.get("/contrato/crear", response_class=HTMLResponse)
def crear_contrato_vista(request: Request, db: Session = Depends(get_db),
                         current_user: DBUsuario = Depends(obtener_usuario_actual)):
    """ Muestra el formulario en blanco para un nuevo contrato """
    return templates.TemplateResponse(
        request=request,
        name="formulario_contrato.html",
        context={
            "request": request,
            "contrato": None,
            "usuario_actual": current_user
        }
    )


@app.get("/contrato/editar_info/{numero_contrato:path}", response_class=HTMLResponse)
def editar_contrato_vista(request: Request, numero_contrato: str, db: Session = Depends(get_db),
                          current_user: DBUsuario = Depends(obtener_usuario_actual)):
    """ Muestra el formulario lleno con los datos existentes """
    tx = GestorTransacciones(db)
    detalle = tx.obtener_detalle_contrato(numero_contrato)
    if not detalle:
        return RedirectResponse(url="/?error=Contrato no encontrado", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="formulario_contrato.html",
        context={
            "request": request,
            "contrato": detalle["contrato"],
            "usuario_actual": current_user
        }
    )


@app.post("/contrato/guardar")
async def registrar_contrato(request: Request, db: Session = Depends(get_db),
                             current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form_data = dict(await request.form())

    # Limpiador de moneda (Quita puntos, comas y signos $)
    def limpiar_dinero(valor):
        if not valor: return 0.0
        val_str = str(valor).replace('$', '').replace(',', '').replace('.', '').strip()
        try:
            return float(val_str)
        except:
            return 0.0

    form_data['valor_total'] = limpiar_dinero(form_data.get('valor_total'))
    form_data['valor_final'] = limpiar_dinero(form_data.get('valor_final'))

    # Si el valor final viene en 0, asume el valor total inicial
    if form_data['valor_final'] == 0:
        form_data['valor_final'] = form_data['valor_total']

    tx = GestorTransacciones(db)
    exito, mensaje = tx.crear_o_actualizar_contrato(form_data)

    if exito:
        return RedirectResponse(url=f"/contrato/{form_data['numero_contrato']}?mensaje={mensaje}", status_code=303)
    return RedirectResponse(url=f"/?error={mensaje}", status_code=303)

@app.get("/contrato/{numero_contrato:path}", response_class=HTMLResponse)
def detalle_contrato(request: Request, numero_contrato: str, mensaje: str = None, error: str = None,
                     db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    detalle = tx.obtener_detalle_contrato(numero_contrato)

    if not detalle:
        return RedirectResponse(url="/?error=Contrato no encontrado", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="detalle_contrato.html",
        context={
            "request": request,
            "contrato": detalle["contrato"],
            "pagos": detalle["pagos"],
            "total_pagado": detalle["total_pagado"],
            "saldo": detalle["saldo"],
            "acumulado_por_girar": detalle["acumulado_historico_pagado"],
            "valor_mensual_sugerido": detalle["valor_mensual_sugerido"],
            "porcentaje": detalle["porcentaje"],
            "proximo_pago": detalle["proximo_pago"],
            "mensaje": mensaje,
            "error": error,
            "usuario_actual": current_user
        }
    )


@app.get("/pago/editar/{pago_id}", response_class=HTMLResponse)
def editar_pago(request: Request, pago_id: int, db: Session = Depends(get_db),
                current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    pago = tx.obtener_pago_por_id(pago_id)
    if not pago:
        return RedirectResponse(url="/?error=Pago no encontrado", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="editar_pago.html",
        context={
            "request": request,
            "pago": pago,
            "usuario_actual": current_user
        }
    )


@app.get("/exportar_excel")
def exportar_excel(numero_contrato: Optional[str] = None, db: Session = Depends(get_db),
                   current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    df = tx.generar_excel_supervisiones(numero_contrato)

    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Supervisiones')
    stream.seek(0)

    if numero_contrato:
        nombre_limpio = numero_contrato.replace("/", "-")
        filename = f"Supervisiones_{nombre_limpio}.xlsx"
    else:
        filename = "Reporte_Supervisiones_Global.xlsx"

    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return StreamingResponse(stream, headers=headers,
                             media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ==========================================
# 4. RUTAS DE ESCRITURA (POST) PROTEGIDAS
# ==========================================

@app.post("/contrato/nuevo")
async def registrar_contrato(request: Request, db: Session = Depends(get_db),
                             current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form_data = dict(await request.form())
    form_data['valor_total'] = float(form_data.get('valor_total') or 0)
    form_data['valor_final'] = float(form_data.get('valor_final') or form_data['valor_total'])

    tx = GestorTransacciones(db)
    exito, mensaje = tx.crear_o_actualizar_contrato(form_data)

    if exito:
        return RedirectResponse(url=f"/contrato/{form_data['numero_contrato']}?mensaje={mensaje}", status_code=303)
    return RedirectResponse(url=f"/?error={mensaje}", status_code=303)


@app.post("/pago/nuevo_completo")
async def registrar_pago_completo(request: Request, db: Session = Depends(get_db),
                                  current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form = dict(await request.form())

    form['eps_nombre'] = form.get("eps_nombre_otro") if form.get("eps_nombre") == "OTRA" else form.get("eps_nombre")
    form['arl_nombre'] = form.get("arl_nombre_otro") if form.get("arl_nombre") == "OTRA" else form.get("arl_nombre")
    form['afp_nombre'] = form.get("afp_nombre_otro") if form.get("afp_nombre") == "OTRA" else form.get("afp_nombre")
    form['ccf_nombre'] = form.get("ccf_nombre_otro") if form.get("ccf_nombre") == "OTRA" else form.get("ccf_nombre")

    campos_numericos = ['numero_pago', 'valor_pagado', 'valor_a_pagar', 'ibc', 'eps_valor', 'arl_valor', 'afp_valor',
                        'sena_valor', 'icbf_valor', 'ccf_valor', 'valor_total_planilla']
    for campo in campos_numericos:
        form[campo] = float(form.get(campo) or 0)

    form_limpio = {k: v for k, v in form.items() if not k.endswith('_otro')}

    if 'numero_contrato' in form_limpio:
        form_limpio['contrato_id'] = form_limpio.pop('numero_contrato')

    tx = GestorTransacciones(db)
    exito, msg = tx.registrar_pago_supervision(form_limpio)

    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/contrato/{form.get('numero_contrato')}?{estado}={msg}", status_code=303)


@app.post("/importar_csv")
async def importar_csv(archivo: UploadFile = File(...), db: Session = Depends(get_db),
                       current_user: DBUsuario = Depends(obtener_usuario_actual)):
    content = await archivo.read()
    try:
        decoded_content = content.decode('utf-8')
    except:
        decoded_content = content.decode('latin-1')

    tx = GestorTransacciones(db)
    exito, msg = tx.importar_datos_csv(decoded_content)

    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/?{estado}={msg}", status_code=303)


@app.post("/pago/actualizar/{pago_id}")
async def procesar_actualizacion(request: Request, pago_id: int, db: Session = Depends(get_db),
                                 current_user: DBUsuario = Depends(obtener_usuario_actual)):
    form = dict(await request.form())

    for entidad in ['eps', 'arl', 'afp', 'ccf']:
        if form.get(f"{entidad}_nombre") == "OTRA":
            form[f"{entidad}_nombre"] = form.get(f"{entidad}_nombre_otro")

    campos_num = ['valor_pagado', 'valor_a_pagar', 'eps_valor', 'arl_valor', 'afp_valor', 'sena_valor', 'icbf_valor',
                  'ccf_valor', 'valor_total_planilla']
    for c in campos_num:
        form[c] = float(form.get(c) or 0)

    form_limpio = {k: v for k, v in form.items() if not k.endswith('_otro')}

    tx = GestorTransacciones(db)
    exito, msg = tx.actualizar_pago_existente(pago_id, form_limpio)

    pago = tx.obtener_pago_por_id(pago_id)
    return RedirectResponse(url=f"/contrato/{pago.contrato_id}?mensaje={msg}", status_code=303)


@app.post("/pago/eliminar/{pago_id}")
async def procesar_borrado_pago(pago_id: int, db: Session = Depends(get_db),
                                current_user: DBUsuario = Depends(obtener_usuario_actual)):
    tx = GestorTransacciones(db)
    pago = tx.obtener_pago_por_id(pago_id)
    if not pago:
        return RedirectResponse(url="/?error=Pago no encontrado", status_code=303)

    id_contrato = pago.contrato_id
    exito, msg = tx.eliminar_pago(pago_id)

    estado = "mensaje" if exito else "error"
    return RedirectResponse(url=f"/contrato/{id_contrato}?{estado}={msg}", status_code=303)


@app.get("/pago/pdf/{pago_id}")
def descargar_pdf_pago(pago_id: int, db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    generador = GeneradorPDF(db, templates)
    # Sin await aquí
    pdf_bytes, nombre_archivo = generador.generar_pdf_pago_unico(pago_id)
    if not pdf_bytes:
        return RedirectResponse(url="/?error=No se pudo generar el PDF", status_code=303)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'})

@app.get("/contratista/{identificacion}/pdfs")
def descargar_pdfs_contratista(identificacion: str, db: Session = Depends(get_db), current_user: DBUsuario = Depends(obtener_usuario_actual)):
    generador = GeneradorPDF(db, templates)
    # Sin await aquí
    zip_buffer = generador.generar_zip_contratista(identificacion)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="Reportes_{identificacion}.zip"'})



# Adaptador AWS
handler = Mangum(app)