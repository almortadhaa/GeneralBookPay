import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask

# إعدادات المحادثة
ID_INPUT, PHONE_VERIFICATION = range(2)

# إعداد التسجيل
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# الاتصال بجوجل شيتس
def connect_google_sheets():
    try:
        # استخدام متغيرات البيئة
        creds_dict = {
            "type": "service_account",
            "project_id": os.getenv('PROJECT_ID'),
            "private_key_id": os.getenv('PRIVATE_KEY_ID'),
            "private_key": os.getenv('PRIVATE_KEY').replace('\\n', '\n'),
            "client_email": os.getenv('CLIENT_EMAIL'),
            "client_id": os.getenv('CLIENT_ID'),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
        }
        
        scope = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(os.getenv('SHEET_ID')).sheet1
        return sheet
    except Exception as e:
        logger.error(f"Error connecting to Google Sheets: {e}")
        return None

# بدء المحادثة
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('مرحباً! 👋 الرجاء إرسال رقم الهوية الخاص بك:')
    return ID_INPUT

# التحقق من الرقم
async def verify_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    employee_id = update.message.text.strip()
    sheet = connect_google_sheets()
    
    if not sheet:
        await update.message.reply_text('⚠️ حدث خطأ في النظام. الرجاء المحاولة لاحقاً.')
        return ConversationHandler.END
    
    try:
        # البحث في العمود A
        cell = sheet.find(employee_id, in_column=1)
        context.user_data['employee_id'] = employee_id
        context.user_data['row'] = cell.row
        
        await update.message.reply_text('✅ تم العثور على الرقم. الرجاء إرسال رقم هاتفك:')
        return PHONE_VERIFICATION
    except gspread.exceptions.CellNotFound:
        await update.message.reply_text('❌ رقم الهوية غير موجود في النظام.')
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in verify_id: {e}")
        await update.message.reply_text('⚠️ حدث خطأ. الرجاء المحاولة لاحقاً.')
        return ConversationHandler.END

# التحقق من الهاتف والحالة
async def verify_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    sheet = connect_google_sheets()
    row = context.user_data.get('row')
    
    if not sheet or not row:
        await update.message.reply_text('⚠️ حدث خطأ في النظام. الرجاء المحاولة لاحقاً.')
        return ConversationHandler.END
    
    try:
        # التحقق من رقم الهاتف في العمود B
        stored_phone = sheet.cell(row, 2).value
        
        if phone == stored_phone:
            # التحقق من الحالة في العمود C
            status = sheet.cell(row, 3).value
            
            if status and status.strip().lower() == 'مسموح':
                # جلب جميع بيانات الموظف
                employee_data = sheet.row_values(row)
                response = f"""
📋 **بيانات الموظف:**

🆔 **رقم الهوية:** {employee_data[0]}
📞 **رقم الهاتف:** {employee_data[1]}
✅ **الحالة:** {employee_data[2]}
📊 **بيانات إضافية:** {', '.join(employee_data[3:]) if len(employee_data) > 3 else 'لا توجد'}
                """
                await update.message.reply_text(response)
            else:
                await update.message.reply_text('❌ عفواً راجع المسؤول الإداري')
        else:
            await update.message.reply_text('❌ رقم الهاتف غير مطابق')
    
    except Exception as e:
        logger.error(f"Error in verify_phone: {e}")
        await update.message.reply_text('⚠️ حدث خطأ. الرجاء المحاولة لاحقاً.')
    
    return ConversationHandler.END

# إلغاء المحادثة
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('تم إلغاء العملية.')
    return ConversationHandler.END

# الدالة الرئيسية
def main():
    # الحصول على التوكن من البيئة
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return
    
    # إنشاء التطبيق
    application = Application.builder().token(TOKEN).build()
    
    # إعداد محادثة التحقق
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ID_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_id)],
            PHONE_VERIFICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_phone)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # بدء البوت
    application.run_polling()

# تطبيق Flask للاستضافة على Koyeb
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

if __name__ == '__main__':
    # تشغيل البوت في خيط منفصل
    from threading import Thread
    bot_thread = Thread(target=main)
    bot_thread.daemon = True
    bot_thread.start()
    
    # تشغيل Flask
    app.run(host='0.0.0.0', port=8000)