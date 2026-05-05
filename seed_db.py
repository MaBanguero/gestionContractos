import os
import sys

# Asegurar que los módulos de la aplicación sean reconocidos
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import SessionLocal, engine
# IMPORTANTE: Se agrega la importación de DBContrato para la actualización masiva
from models.db_models import Base, DBPerfil, DBActividadPerfil, DBContrato
from services.pdf_generator import ACTIVIDADES_POR_PERFIL, HONORARIOS_POR_PERFIL


def inicializar_base_de_datos():
    """
    Script de migración atómica:
    1. Verifica la existencia de las tablas.
    2. Itera sobre los diccionarios estáticos de perfiles y honorarios.
    3. Inyecta los datos en la base de datos relacional evitando duplicados.
    4. Actualiza masivamente los contratos existentes asignándoles la Resolución 1010.
    """
    print(">>> Iniciando migración de datos (Seed Process) ...")

    # Asegura que las nuevas tablas existan en SQLite/PostgreSQL
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        perfiles_creados = 0
        actividades_creadas = 0

        # --- 1. INYECCIÓN DE PERFILES Y OBLIGACIONES ---
        for nombre_perfil, lista_actividades in ACTIVIDADES_POR_PERFIL.items():
            perfil_limpio = nombre_perfil.strip().upper()

            # Buscar si el perfil ya existe en la BD
            perfil_db = db.query(DBPerfil).filter(DBPerfil.nombre == perfil_limpio).first()

            if not perfil_db:
                # Recuperar el honorario base del diccionario (si no existe, asigna 0.0)
                honorario_base = float(HONORARIOS_POR_PERFIL.get(perfil_limpio, 0.0))

                # Insertar nuevo perfil incluyendo su honorario de referencia
                perfil_db = DBPerfil(
                    nombre=perfil_limpio,
                    descripcion="Migrado desde configuración estática.",
                    honorario_referencia=honorario_base
                )
                db.add(perfil_db)
                db.flush()  # Vacía el registro para obtener el ID asignado por la BD
                perfiles_creados += 1

                # Inyectar las actividades (ordenadas según la lista original)
                for index, descripcion_actividad in enumerate(lista_actividades, start=1):
                    actividad_db = DBActividadPerfil(
                        perfil_id=perfil_db.id,
                        descripcion=descripcion_actividad.strip(),
                        orden=index
                    )
                    db.add(actividad_db)
                    actividades_creadas += 1
            else:
                print(f"[-] El perfil {perfil_limpio} ya existe. Omitiendo para evitar duplicidad.")

        # --- 2. ACTUALIZACIÓN MASIVA DE CONTRATOS (RESOLUCIÓN 1010) ---
        # Actualiza todos los contratos donde la resolución sea NULL o esté vacía
        contratos_actualizados = db.query(DBContrato).filter(
            (DBContrato.resolucion == None) | (DBContrato.resolucion == "")
        ).update({"resolucion": "1010"}, synchronize_session=False)

        db.commit()
        print(f">>> Migración finalizada con éxito.")
        print(f">>> Perfiles creados: {perfiles_creados}")
        print(f">>> Obligaciones insertadas: {actividades_creadas}")
        print(f">>> Contratos actualizados con Resolución 1010: {contratos_actualizados}")

    except Exception as e:
        db.rollback()
        print(f"!!! Error Crítico durante la migración: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    inicializar_base_de_datos()