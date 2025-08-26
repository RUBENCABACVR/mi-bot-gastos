import logging
import sqlite3
from datetime import datetime, timedelta
import csv
import io
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelevel)s - %(message)s',
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

class ExpenseBot:
    def __init__(self, db_path='gastos.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializa la base de datos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                monto REAL NOT NULL,
                descripcion TEXT,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS presupuestos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                limite REAL NOT NULL,
                mes TEXT NOT NULL,
                UNIQUE(user_id, categoria, mes)
            )
        ''')
        
        conn.commit()
        conn.close()
    
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
    
    def obtener_gastos_por_categoria(self, user_id, categoria, dias=30):
        """Obtiene gastos de una categoría específica"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        fecha_limite = datetime.now() - timedelta(days=dias)
        
        cursor.execute('''
            SELECT * FROM gastos 
            WHERE user_id = ? AND categoria = ? AND fecha >= ?
            ORDER BY fecha DESC
        ''', (user_id, categoria, fecha_limite))
        
        gastos = cursor.fetchall()
        conn.close()
        return gastos
    
    def obtener_resumen_mensual(self, user_id):
        """Obtiene resumen mensual por categoría"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        primer_dia_mes = datetime.now().replace(day=1)
        
        cursor.execute('''
            SELECT categoria, SUM(monto) as total
            FROM gastos 
            WHERE user_id = ? AND fecha >= ?
            GROUP BY categoria
            ORDER BY total DESC
        ''', (user_id, primer_dia_mes))
        
        resumen = cursor.fetchall()
        conn.close()
        return resumen
    
    def exportar_gastos_csv(self, user_id):
        """Exporta gastos a CSV"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fecha, categoria, monto, descripcion
            FROM gastos 
            WHERE user_id = ?
            ORDER BY fecha DESC
        ''', (user_id,))
        
        gastos = cursor.fetchall()
        conn.close()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Fecha', 'Categoría', 'Monto', 'Descripción'])
        
        for gasto in gastos:
            fecha = datetime.fromisoformat(gasto[0]).strftime('%Y-%m-%d %H:%M')
            categoria = CATEGORIAS.get(gasto[1], gasto[1])
            writer.writerow([fecha, categoria, gasto[2], gasto[3] or ''])
        
        return output.getvalue()

# Instancia del bot
expense_bot = ExpenseBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start"""
    keyboard = [
        [KeyboardButton("💰 Agregar Gasto"), KeyboardButton("📊 Ver Resumen")],
        [KeyboardButton("📈 Estadísticas"), KeyboardButton("📥 Exportar Datos")],
        [KeyboardButton("⚙️ Configuración")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_text(
        "¡Hola! 👋 Soy tu asistente de gestión de gastos.\n\n"
        "Puedo ayudarte a:\n"
        "• 💰 Registrar gastos por categoría\n"
        "• 📊 Ver resúmenes y estadísticas\n"
        "• 📥 Exportar tus datos\n"
        "• ⚙️ Configurar presupuestos\n\n"
        "¿Qué te gustaría hacer?",
        reply_markup=reply_markup
    )

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
        "Selecciona la categoría del gasto:",
        reply_markup=reply_markup
    )

async def callback_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja la selección de categoría"""
    query = update.callback_query
    await query.answer()
    
    categoria = query.data.replace('categoria_', '')
    context.user_data['categoria'] = categoria
    
    await query.edit_message_text(
        f"Has seleccionado: {CATEGORIAS[categoria]}\n\n"
        "Ahora envía el monto y descripción del gasto.\n"
        "Formato: `monto descripción`\n"
        "Ejemplo: `50000 hamburguesa`",
        parse_mode='Markdown'
    )

async def procesar_gasto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa el gasto ingresado por el usuario"""
    if 'categoria' not in context.user_data:
        await update.message.reply_text(
            "Primero selecciona una categoría usando el botón '💰 Agregar Gasto'"
        )
        return
    
    try:
        texto = update.message.text.strip()
        partes = texto.split(' ', 1)
        
        monto = float(partes[0].replace(',', '').replace('.', ''))
        descripcion = partes[1] if len(partes) > 1 else ""
        
        categoria = context.user_data['categoria']
        user_id = update.effective_user.id
        
        expense_bot.agregar_gasto(user_id, categoria, monto, descripcion)
        
        await update.message.reply_text(
            f"✅ ¡Gasto registrado con éxito!\n\n"
            f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"📂 Categoría: {CATEGORIAS[categoria]}\n"
            f"💰 Monto: ${monto:,.0f}\n"
            f"📝 Descripción: {descripcion or 'Sin descripción'}"
        )
        
        # Limpiar datos temporales
        context.user_data.clear()
        
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Formato incorrecto. Usa: `monto descripción`\n"
            "Ejemplo: `50000 hamburguesa`",
            parse_mode='Markdown'
        )

async def ver_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra resumen mensual"""
    user_id = update.effective_user.id
    resumen = expense_bot.obtener_resumen_mensual(user_id)
    
    if not resumen:
        await update.message.reply_text("No tienes gastos registrados este mes.")
        return
    
    texto = "📊 *Resumen del mes actual:*\n\n"
    total_general = 0
    
    for categoria, total in resumen:
        emoji_categoria = CATEGORIAS.get(categoria, categoria)
        texto += f"{emoji_categoria}: ${total:,.0f}\n"
        total_general += total
    
    texto += f"\n💳 *Total del mes: ${total_general:,.0f}*"
    
    await update.message.reply_text(texto, parse_mode='Markdown')

async def exportar_datos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exporta datos a CSV"""
    user_id = update.effective_user.id
    csv_data = expense_bot.exportar_gastos_csv(user_id)
    
    if not csv_data.strip():
        await update.message.reply_text("No tienes gastos para exportar.")
        return
    
    # Crear archivo CSV en memoria
    csv_bytes = csv_data.encode('utf-8')
    csv_file = io.BytesIO(csv_bytes)
    csv_file.name = f'gastos_{datetime.now().strftime("%Y%m%d")}.csv'
    
    await update.message.reply_document(
        document=csv_file,
        filename=csv_file.name,
        caption="📥 Aquí tienes tu reporte de gastos en formato CSV"
    )

async def estadisticas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra estadísticas detalladas"""
    keyboard = [
        [InlineKeyboardButton("📅 Últimos 7 días", callback_data='stats_7')],
        [InlineKeyboardButton("📅 Últimos 30 días", callback_data='stats_30')],
        [InlineKeyboardButton("📅 Últimos 90 días", callback_data='stats_90')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📈 Selecciona el período para ver estadísticas:",
        reply_markup=reply_markup
    )

async def callback_estadisticas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja las estadísticas por período"""
    query = update.callback_query
    await query.answer()
    
    dias = int(query.data.replace('stats_', ''))
    user_id = update.effective_user.id
    
    # Aquí puedes implementar lógica más detallada para estadísticas
    await query.edit_message_text(f"📊 Estadísticas de los últimos {dias} días\n(Función en desarrollo)")

async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja todos los mensajes de texto"""
    texto = update.message.text
    
    if texto == "💰 Agregar Gasto":
        await agregar_gasto_inicio(update, context)
    elif texto == "📊 Ver Resumen":
        await ver_resumen(update, context)
    elif texto == "📈 Estadísticas":
        await estadisticas(update, context)
    elif texto == "📥 Exportar Datos":
        await exportar_datos(update, context)
    elif texto == "⚙️ Configuración":
        await update.message.reply_text("⚙️ Configuración (próximamente)")
    else:
        # Si hay una categoría seleccionada, procesar como gasto
        if 'categoria' in context.user_data:
            await procesar_gasto(update, context)
        else:
            await update.message.reply_text(
                "Usa los botones del menú para interactuar conmigo 😊"
            )

def main():
    """Función principal"""
    # AQUÍ DEBES PONER TU TOKEN
    TOKEN = os.environ.get('TOKEN')
    
    application = Application.builder().token(TOKEN).build()
    
    # Comandos
    application.add_handler(CommandHandler("start", start))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(callback_categoria, pattern='^categoria_'))
    application.add_handler(CallbackQueryHandler(callback_estadisticas, pattern='^stats_'))
    
    # Mensajes de texto
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))
    
    # Iniciar bot
    print("🤖 Bot iniciado...")
    application.run_polling()

if __name__ == '__main__':

    main()

