import logging
import sqlite3
from datetime import datetime, timedelta, date
import csv
import io
import calendar
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Categorías de gastos con emojis
CATEGORIAS = {
    'alimentacion': '🥦 Alimentación',
    'vivienda': '🏠 Vivienda',
    'transporte': '🚗 Transporte',
    'salud': '🏥 Salud',
    'educacion': '🎓 Educación',
    'tecnologia': '💻 Tecnología',
    'finanzas': '💰 Finanzas',
    'seguros': '🛡️ Seguros',
    'entretenimiento': '🎮 Entretenimiento',
    'ropa': '👕 Ropa',
    'otros': '📝 Otros'
}

class AdvancedExpenseBot:
    def __init__(self, db_path='gastos_avanzado.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializa la base de datos con tablas avanzadas"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabla de gastos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                monto REAL NOT NULL,
                descripcion TEXT,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                es_recurrente BOOLEAN DEFAULT 0,
                gasto_recurrente_id INTEGER
            )
        ''')
        
        # Tabla de presupuesto mensual general
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS presupuesto_mensual (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                año INTEGER NOT NULL,
                monto_inicial REAL NOT NULL,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, mes, año)
            )
        ''')
        
        # Nueva tabla: Presupuestos por categoría
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS presupuesto_categoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                mes INTEGER NOT NULL,
                año INTEGER NOT NULL,
                monto_asignado REAL NOT NULL,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, categoria, mes, año)
            )
        ''')
        
        # Nueva tabla: Gastos recurrentes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gastos_recurrentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                monto REAL NOT NULL,
                dia_del_mes INTEGER NOT NULL,
                activo BOOLEAN DEFAULT 1,
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                ultimo_procesamiento DATE
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def establecer_presupuesto_mensual(self, user_id, monto):
        """Establece el presupuesto general del mes"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        hoy = datetime.now()
        mes_actual = hoy.month
        año_actual = hoy.year
        
        cursor.execute('''
            INSERT OR REPLACE INTO presupuesto_mensual (user_id, mes, año, monto_inicial)
            VALUES (?, ?, ?, ?)
        ''', (user_id, mes_actual, año_actual, monto))
        
        conn.commit()
        conn.close()
    
    def establecer_presupuesto_categoria(self, user_id, categoria, monto):
        """Establece presupuesto específico para una categoría"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        hoy = datetime.now()
        mes_actual = hoy.month
        año_actual = hoy.year
        
        cursor.execute('''
            INSERT OR REPLACE INTO presupuesto_categoria (user_id, categoria, mes, año, monto_asignado)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, categoria, mes_actual, año_actual, monto))
        
        conn.commit()
        conn.close()
    
    def crear_gasto_recurrente(self, user_id, categoria, descripcion, monto, dia_del_mes):
        """Crea un gasto recurrente"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO gastos_recurrentes (user_id, categoria, descripcion, monto, dia_del_mes)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, categoria, descripcion, monto, dia_del_mes))
        
        conn.commit()
        conn.close()
        return cursor.lastrowid
    
    def obtener_gastos_recurrentes(self, user_id):
        """Obtiene todos los gastos recurrentes activos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, categoria, descripcion, monto, dia_del_mes, ultimo_procesamiento
            FROM gastos_recurrentes 
            WHERE user_id = ? AND activo = 1
            ORDER BY dia_del_mes ASC
        ''', (user_id,))
        
        gastos = cursor.fetchall()
        conn.close()
        return gastos
    
    def procesar_gastos_recurrentes_pendientes(self, user_id):
        """Procesa gastos recurrentes que deben ejecutarse este mes"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        hoy = date.today()
        primer_dia_mes = hoy.replace(day=1)
        
        # Obtener gastos recurrentes que deben procesarse
        cursor.execute('''
            SELECT id, categoria, descripcion, monto, dia_del_mes
            FROM gastos_recurrentes 
            WHERE user_id = ? AND activo = 1 
            AND (ultimo_procesamiento IS NULL OR ultimo_procesamiento < ?)
            AND dia_del_mes <= ?
        ''', (user_id, primer_dia_mes, hoy.day))
        
        gastos_pendientes = cursor.fetchall()
        gastos_procesados = []
        
        for gasto_id, categoria, descripcion, monto, dia_del_mes in gastos_pendientes:
            # Crear el gasto
            cursor.execute('''
                INSERT INTO gastos (user_id, categoria, monto, descripcion, es_recurrente, gasto_recurrente_id)
                VALUES (?, ?, ?, ?, 1, ?)
            ''', (user_id, categoria, monto, f"{descripcion} (Recurrente)", gasto_id))
            
            # Actualizar fecha de último procesamiento
            cursor.execute('''
                UPDATE gastos_recurrentes 
                SET ultimo_procesamiento = ? 
                WHERE id = ?
            ''', (hoy, gasto_id))
            
            gastos_procesados.append({
                'categoria': categoria,
                'descripcion': descripcion,
                'monto': monto,
                'dia': dia_del_mes
            })
        
        conn.commit()
        conn.close()
        return gastos_procesados
    
    def obtener_resumen_por_categoria(self, user_id):
        """Obtiene resumen de gastos vs presupuesto por categoría"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        hoy = datetime.now()
        mes_actual = hoy.month
        año_actual = hoy.year
        primer_dia_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Obtener gastos del mes por categoría
        cursor.execute('''
            SELECT categoria, SUM(monto) as gastado
            FROM gastos 
            WHERE user_id = ? AND fecha >= ?
            GROUP BY categoria
        ''', (user_id, primer_dia_mes))
        
        gastos_categoria = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Obtener presupuestos por categoría
        cursor.execute('''
            SELECT categoria, monto_asignado
            FROM presupuesto_categoria 
            WHERE user_id = ? AND mes = ? AND año = ?
        ''', (user_id, mes_actual, año_actual))
        
        presupuestos_categoria = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        # Combinar información
        resumen = {}
        todas_categorias = set(gastos_categoria.keys()) | set(presupuestos_categoria.keys())
        
        for categoria in todas_categorias:
            gastado = gastos_categoria.get(categoria, 0)
            presupuesto = presupuestos_categoria.get(categoria, 0)
            saldo = presupuesto - gastado
            porcentaje = (gastado / presupuesto * 100) if presupuesto > 0 else 0
            
            resumen[categoria] = {
                'gastado': gastado,
                'presupuesto': presupuesto,
                'saldo': saldo,
                'porcentaje': porcentaje
            }
        
        return resumen
    
    def obtener_comparacion_mes_anterior(self, user_id):
        """Compara gastos del mes actual vs mes anterior"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        hoy = datetime.now()
        
        # Mes actual
        primer_dia_mes_actual = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Mes anterior
        if hoy.month == 1:
            mes_anterior = datetime(hoy.year - 1, 12, 1)
            ultimo_dia_mes_anterior = datetime(hoy.year, 1, 1) - timedelta(days=1)
        else:
            mes_anterior = hoy.replace(month=hoy.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            ultimo_dia_mes_anterior = primer_dia_mes_actual - timedelta(days=1)
        
        # Gastos mes actual
        cursor.execute('''
            SELECT SUM(monto) FROM gastos 
            WHERE user_id = ? AND fecha >= ?
        ''', (user_id, primer_dia_mes_actual))
        
        total_actual = cursor.fetchone()[0] or 0
        
        # Gastos mes anterior
        cursor.execute('''
            SELECT SUM(monto) FROM gastos 
            WHERE user_id = ? AND fecha BETWEEN ? AND ?
        ''', (user_id, mes_anterior, ultimo_dia_mes_anterior))
        
        total_anterior = cursor.fetchone()[0] or 0
        
        conn.close()
        
        diferencia = total_actual - total_anterior
        porcentaje_cambio = (diferencia / total_anterior * 100) if total_anterior > 0 else 0
        
        return {
            'mes_actual': total_actual,
            'mes_anterior': total_anterior,
            'diferencia': diferencia,
            'porcentaje_cambio': porcentaje_cambio
        }
    
    def proyeccion_fin_mes(self, user_id):
        """Proyecta gastos para fin de mes basado en tendencia actual"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        hoy = datetime.now()
        primer_dia_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        dias_transcurridos = (hoy - primer_dia_mes).days + 1
        dias_del_mes = calendar.monthrange(hoy.year, hoy.month)[1]
        
        cursor.execute('''
            SELECT SUM(monto) FROM gastos 
            WHERE user_id = ? AND fecha >= ?
        ''', (user_id, primer_dia_mes))
        
        total_actual = cursor.fetchone()[0] or 0
        conn.close()
        
        if dias_transcurridos > 0:
            promedio_diario = total_actual / dias_transcurridos
            proyeccion = promedio_diario * dias_del_mes
        else:
            proyeccion = 0
        
        return {
            'total_actual': total_actual,
            'dias_transcurridos': dias_transcurridos,
            'dias_restantes': dias_del_mes - dias_transcurridos,
            'promedio_diario': promedio_diario if dias_transcurridos > 0 else 0,
            'proyeccion_fin_mes': proyeccion
        }
    
    def agregar_gasto(self, user_id, categoria, monto, descripcion):
        """Agrega un nuevo gasto"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO gastos (user_id, categoria, monto, descripcion)
            VALUES (?, ?, ?, ?)
        ''', (user_id, categoria, monto, descripcion))
        
        conn.commit()
        conn.close()

# Instancia del bot
expense_bot = AdvancedExpenseBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start con procesamiento automático de recurrentes"""
    user_id = update.effective_user.id
    
    # Procesar gastos recurrentes pendientes
    gastos_procesados = expense_bot.procesar_gastos_recurrentes_pendientes(user_id)
    
    keyboard = [
        [KeyboardButton("💰 Presupuesto General"), KeyboardButton("🎯 Presupuesto por Categoría")],
        [KeyboardButton("🔄 Gastos Recurrentes"), KeyboardButton("📊 Estado Detallado")],
        [KeyboardButton("🛒 Agregar Gasto"), KeyboardButton("📈 Análisis y Tendencias")],
        [KeyboardButton("📋 Resumen Completo")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    mensaje = "Soy tu gestor financiero avanzado.\n\n"
    
    if gastos_procesados:
        mensaje += f"Se procesaron {len(gastos_procesados)} gastos recurrentes:\n"
        for gasto in gastos_procesados:
            mensaje += f"• {CATEGORIAS.get(gasto['categoria'], gasto['categoria'])}: ${gasto['monto']:,.0f}\n"
        mensaje += "\n"
    
    mensaje += "Funcionalidades disponibles:\n"
    mensaje += "• Presupuestos por categoría\n"
    mensaje += "• Gastos recurrentes automáticos\n"
    mensaje += "• Análisis de tendencias\n"
    mensaje += "• Proyecciones inteligentes"
    
    await update.message.reply_text(mensaje, reply_markup=reply_markup)

async def configurar_presupuesto_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configurar presupuestos por categoría"""
    keyboard = []
    row = []
    
    for key, value in CATEGORIAS.items():
        row.append(InlineKeyboardButton(value, callback_data=f'presup_cat_{key}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Selecciona la categoría para asignar presupuesto:",
        reply_markup=reply_markup
    )

async def gestionar_gastos_recurrentes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestionar gastos recurrentes"""
    user_id = update.effective_user.id
    gastos = expense_bot.obtener_gastos_recurrentes(user_id)
    
    mensaje = "Gastos Recurrentes Activos:\n\n"
    
    if gastos:
        for gasto_id, categoria, descripcion, monto, dia, ultimo_proc in gastos:
            emoji = CATEGORIAS.get(categoria, categoria)
            mensaje += f"{emoji}\n"
            mensaje += f"📝 {descripcion}\n"
            mensaje += f"💰 ${monto:,.0f} cada día {dia}\n"
            if ultimo_proc:
                mensaje += f"📅 Último: {ultimo_proc}\n"
            mensaje += f"🆔 ID: {gasto_id}\n\n"
    else:
        mensaje += "No tienes gastos recurrentes configurados.\n\n"
    
    mensaje += "Comandos:\n"
    mensaje += "• /nuevo_recurrente - Crear gasto recurrente\n"
    mensaje += "• /eliminar_recurrente <id> - Eliminar recurrente"
    
    await update.message.reply_text(mensaje)

async def estado_detallado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Estado detallado con presupuestos por categoría"""
    user_id = update.effective_user.id
    resumen_categorias = expense_bot.obtener_resumen_por_categoria(user_id)
    
    if not resumen_categorias:
        await update.message.reply_text(
            "No hay presupuestos configurados por categoría.\n"
            "Usa 'Presupuesto por Categoría' para comenzar."
        )
        return
    
    mensaje = "ESTADO DETALLADO POR CATEGORÍA\n\n"
    
    total_presupuesto = 0
    total_gastado = 0
    alertas = []
    
    for categoria, datos in resumen_categorias.items():
        emoji = CATEGORIAS.get(categoria, categoria)
        
        estado = ""
        if datos['porcentaje'] > 100:
            estado = " EXCEDIDO"
            alertas.append(f"{emoji} excedido en ${abs(datos['saldo']):,.0f}")
        elif datos['porcentaje'] > 80:
            estado = " ALERTA"
            alertas.append(f"{emoji} cerca del límite")
        
        mensaje += f"{emoji}{estado}\n"
        mensaje += f"💰 Presupuesto: ${datos['presupuesto']:,.0f}\n"
        mensaje += f"💸 Gastado: ${datos['gastado']:,.0f} ({datos['porcentaje']:.1f}%)\n"
        mensaje += f"💵 Disponible: ${datos['saldo']:,.0f}\n\n"
        
        total_presupuesto += datos['presupuesto']
        total_gastado += datos['gastado']
    
    mensaje += f"RESUMEN GENERAL\n"
    mensaje += f"💰 Presupuesto total: ${total_presupuesto:,.0f}\n"
    mensaje += f"💸 Total gastado: ${total_gastado:,.0f}\n"
    mensaje += f"💵 Saldo general: ${total_presupuesto - total_gastado:,.0f}\n"
    
    if alertas:
        mensaje += f"\nALERTAS:\n"
        for alerta in alertas:
            mensaje += f"⚠️ {alerta}\n"
    
    await update.message.reply_text(mensaje)

async def analisis_tendencias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Análisis de tendencias y proyecciones"""
    user_id = update.effective_user.id
    comparacion = expense_bot.obtener_comparacion_mes_anterior(user_id)
    proyeccion = expense_bot.proyeccion_fin_mes(user_id)
    
    mensaje = "ANÁLISIS DE TENDENCIAS\n\n"
    
    # Comparación mes anterior
    mensaje += "📊 COMPARACIÓN MENSUAL\n"
    mensaje += f"📅 Mes actual: ${comparacion['mes_actual']:,.0f}\n"
    mensaje += f"📅 Mes anterior: ${comparacion['mes_anterior']:,.0f}\n"
    
    if comparacion['diferencia'] > 0:
        mensaje += f"📈 Incremento: ${comparacion['diferencia']:,.0f} (+{comparacion['porcentaje_cambio']:.1f}%)\n"
    elif comparacion['diferencia'] < 0:
        mensaje += f"📉 Reducción: ${abs(comparacion['diferencia']):,.0f} (-{abs(comparacion['porcentaje_cambio']):.1f}%)\n"
    else:
        mensaje += "➖ Sin cambios\n"
    
    mensaje += f"\n🔮 PROYECCIÓN FIN DE MES\n"
    mensaje += f"📊 Promedio diario: ${proyeccion['promedio_diario']:,.0f}\n"
    mensaje += f"📈 Proyección total: ${proyeccion['proyeccion_fin_mes']:,.0f}\n"
    mensaje += f"📅 Días transcurridos: {proyeccion['dias_transcurridos']}\n"
    mensaje += f"⏰ Días restantes: {proyeccion['dias_restantes']}\n"
    
    # Recomendación
    if proyeccion['dias_restantes'] > 0:
        gasto_diario_recomendado = (comparacion['mes_anterior'] - proyeccion['total_actual']) / proyeccion['dias_restantes']
        if gasto_diario_recomendado > 0:
            mensaje += f"\n💡 RECOMENDACIÓN\n"
            mensaje += f"Para igualar el mes anterior, gasta máximo ${gasto_diario_recomendado:,.0f}/día"
    
    await update.message.reply_text(mensaje)

async def agregar_gasto_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inicia el proceso de agregar gasto"""
    keyboard = []
    row = []
    
    for key, value in CATEGORIAS.items():
        row.append(InlineKeyboardButton(value, callback_data=f'categoria_{key}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛒 Selecciona la categoría del gasto:",
        reply_markup=reply_markup
    )

async def callback_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja la selección de categoría para gastos"""
    query = update.callback_query
    await query.answer()
    
    categoria = query.data.replace('categoria_', '')
    context.user_data['categoria'] = categoria
    
    await query.edit_message_text(
        f"Has seleccionado: {CATEGORIAS[categoria]}\n\n"
        "Ahora envía el monto y descripción del gasto.\n"
        "Formato: monto descripción\n"
        "Ejemplo: 50000 hamburguesa"
    )

async def callback_presupuesto_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja selección de categoría para presupuesto"""
    query = update.callback_query
    await query.answer()
    
    categoria = query.data.replace('presup_cat_', '')
    context.user_data['categoria_presupuesto'] = categoria
    
    await query.edit_message_text(
        f"Has seleccionado: {CATEGORIAS[categoria]}\n\n"
        "Envía el monto del presupuesto para esta categoría.\n"
        "Ejemplo: 1500"
    )

async def procesar_gasto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa el gasto ingresado por el usuario"""
    if 'categoria' not in context.user_data:
        await update.message.reply_text(
            "Primero selecciona una categoría usando 'Agregar Gasto'"
        )
        return
    
    try:
        texto = update.message.text.strip()
        partes = texto.split(' ', 1)
        
        monto = float(partes[0].replace(',', ''))
        descripcion = partes[1] if len(partes) > 1 else ""
        
        categoria = context.user_data['categoria']
        user_id = update.effective_user.id
        
        expense_bot.agregar_gasto(user_id, categoria, monto, descripcion)
        
        respuesta = f"✅ Gasto registrado:\n"
        respuesta += f"📂 {CATEGORIAS[categoria]}\n"
        respuesta += f"💰 ${monto:,.0f}\n"
        respuesta += f"📝 {descripcion or 'Sin descripción'}"
        
        await update.message.reply_text(respuesta)
        context.user_data.clear()
        
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Formato incorrecto. Usa: monto descripción\n"
            "Ejemplo: 50000 hamburguesa"
        )

async def nuevo_recurrente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para crear nuevo gasto recurrente"""
    await update.message.reply_text(
        "Crear nuevo gasto recurrente:\n\n"
        "Formato: /nuevo_recurrente <categoría> <día> <monto> <descripción>\n\n"
        "Ejemplo: /nuevo_recurrente alimentacion 15 800 Supermercado mensual\n\n"
        "Categorías disponibles: " + ", ".join(CATEGORIAS.keys())
    )

async def procesar_nuevo_recurrente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa la creación de un gasto recurrente"""
    if len(context.args) < 4:
        await update.message.reply_text(
            "Formato incorrecto. Usa:\n"
            "/nuevo_recurrente <categoría> <día> <monto> <descripción>"
        )
        return
    
    try:
        categoria = context.args[0].lower()
        dia = int(context.args[1])
        monto = float(context.args[2])
        descripcion = ' '.join(context.args[3:])
        
        if categoria not in CATEGORIAS:
            await update.message.reply_text("Categoría no válida")
            return
        
        if dia < 1 or dia > 31:
            await update.message.reply_text("El día debe estar entre 1 y 31")
            return
        
        user_id = update.effective_user.id
        gasto_id = expense_bot.crear_gasto_recurrente(user_id, categoria, descripcion, monto, dia)
        
        await update.message.reply_text(
            f"Gasto recurrente creado:\n"
            f"🆔 ID: {gasto_id}\n"
            f"📂 {CATEGORIAS[categoria]}\n"
            f"💰 ${monto:,.0f}\n"
            f"📅 Cada día {dia}\n"
            f"📝 {descripcion}\n\n"
            f"Se procesará automáticamente cada mes."
        )
        
    except ValueError:
        await update.message.reply_text("Error en el formato. Verifica día y monto.")

async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja todos los mensajes de texto"""
    texto = update.message.text
    
    if texto == "🎯 Presupuesto por Categoría":
        await configurar_presupuesto_categoria(update, context)
    elif texto == "🔄 Gastos Recurrentes":
        await gestionar_gastos_recurrentes(update, context)
    elif texto == "📊 Estado Detallado":
        await estado_detallado(update, context)
    elif texto == "📈 Análisis y Tendencias":
        await analisis_tendencias(update, context)
    elif texto == "🛒 Agregar Gasto":
        await agregar_gasto_inicio(update, context)
    elif context.user_data.get('categoria_presupuesto'):
        # Procesar monto de presupuesto por categoría
        try:
            monto = float(texto.replace(',', ''))
            categoria = context.user_data['categoria_presupuesto']
            user_id = update.effective_user.id
            
            expense_bot.establecer_presupuesto_categoria(user_id, categoria, monto)
            
            await update.message.reply_text(
                f"Presupuesto establecido:\n"
                f"📂 {CATEGORIAS[categoria]}\n"
                f"💰 ${monto:,.0f}\n\n"
                f"¡Ya puedes monitorear los gastos de esta categoría!"
            )
            context.user_data.clear()
        except ValueError:
            await update.message.reply_text("Por favor ingresa un número válido")
    else:
        # Si hay una categoría seleccionada, procesar como gasto
        if 'categoria' in context.user_data:
            await procesar_gasto(update, context)
        else:
            await update.message.reply_text(
                "Usa los botones del menú para interactuar conmigo"
            )

def main():
    """Función principal"""
    TOKEN = '8165111585:AAHuaV1P5IAI7AM0dinpTZlDa0QXYM0rDOs'
    
    application = Application.builder().token(TOKEN).build()
    
    # Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("nuevo_recurrente", procesar_nuevo_recurrente))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(callback_presupuesto_categoria, pattern='^presup_cat_'))
    application.add_handler(CallbackQueryHandler(callback_categoria, pattern='^categoria_'))
    
    # Mensajes de texto
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))
    
    print("Bot de gastos avanzado iniciado...")
    application.run_polling()

if __name__ == '__main__':
    main()
