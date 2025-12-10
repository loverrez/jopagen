from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import os
from truemoney_api import TrueMoneyWallet

# ==========================================
ADMIN_USERNAME = "thanathip"    # ชื่อผู้ใช้แอดมิน
ADMIN_PASSWORD = "thanathip" # รหัสผ่านแอดมิน
# ==========================================

app = Flask(__name__)
app.secret_key = "MY_SUPER_SECRET_KEY_CHANGE_THIS" 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), default='member')
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500), default="https://placehold.co/300x200")
    description = db.Column(db.String(200), default="")

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_sold = db.Column(db.Boolean, default=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_name = db.Column(db.String(100))
    price = db.Column(db.Float) # ตัวนี้คือราคาที่ใช้ในการสั่งซื้อ
    data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

class TopupHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(50), default='truemoney_gift')
    status = db.Column(db.String(20), default='pending') 
    ref = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship('User', backref='topups')

class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    order = db.Column(db.Integer, default=0)

class SiteConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(100), default="JOPA GEN")
    logo_url = db.Column(db.String(500), default="")
    announcement = db.Column(db.Text, default="[ อยู่ในช่วง Version.Test]")
    contact_url = db.Column(db.String(500), default="https://discord.gg/yourlink")
    truemoney_phone = db.Column(db.String(10), default="")

# --- Helpers ---
def get_config():
    conf = SiteConfig.query.first()
    if not conf:
        conf = SiteConfig()
        db.session.add(conf)
        db.session.commit()
    return conf

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("กรุณาเข้าสู่ระบบ", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("กรุณาเข้าสู่ระบบ", "error")
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            flash("คุณไม่มีสิทธิ์เข้าถึงหน้านี้", "error")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---
@app.before_request
def before_request():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            # ทำให้ current_user ใช้งานได้ในทุก template
            # (ต้องเพิ่ม current_user ใน context processor ถ้าจะใช้แบบนี้)
            pass 
        else:
            session.pop('user_id', None)

@app.context_processor
def inject_globals():
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
    
    # ดึง config ทุกครั้ง
    conf = get_config()

    return dict(current_user=user, site_config=conf)

@app.route('/')
def home():
    conf = get_config()
    banners = Banner.query.order_by(Banner.order).all()
    
    latest_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    orders_for_template = []
    
    for order in latest_orders:
        user_obj = User.query.get(order.user_id)
        
        orders_for_template.append({
            'user': user_obj.username if user_obj else 'Guest',
            'item': order.category_name,
            'price': order.price,
            'time': order.created_at.strftime("%H:%M:%S") 
        })
    
    return render_template('home.html', 
        site_banners=banners, 
        site_config=conf,
        orders=orders_for_template
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm_password']

        if password != confirm:
            flash("รหัสผ่านไม่ตรงกัน", "error")
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash("ชื่อผู้ใช้นี้ถูกใช้แล้ว", "error")
            return redirect(url_for('register'))

        new_user = User(username=username, password=generate_password_hash(password))

        if username == ADMIN_USERNAME:
            new_user.role = 'admin'
            new_user.balance = 100000000
            
        db.session.add(new_user)
        db.session.commit()

        flash("สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            flash(f"ยินดีต้อนรับ, {user.username}", "success")
            return redirect(url_for('home'))

        flash("ชื่อผู้ใช้หรือรหัสผ่านผิด", "error")
        
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("ออกจากระบบเรียบร้อย", "success")
    return redirect(url_for('home'))

@app.route('/idgen', methods=['GET', 'POST'])
@login_required
def idgen():
    categories = Category.query.all()
    user = User.query.get(session['user_id'])
    
    # ดึงจำนวนสต็อกที่เหลือ
    stock_counts = db.session.query(Stock.category_id, db.func.count(Stock.id)).filter(Stock.is_sold == False).group_by(Stock.category_id).all()
    stock_map = {cat_id: count for cat_id, count in stock_counts}

    if request.method == 'POST':
        cat_id = request.form.get('category_id')
        qty = int(request.form.get('quantity', 1))
        
        # 1. ตรวจสอบข้อมูล
        category = Category.query.get(cat_id)
        if not category:
            flash("ไม่พบหมวดหมู่สินค้า", "error")
            return redirect(url_for('idgen'))

        required_stock = qty
        total_price = category.price * qty
        
        # 2. ตรวจสอบสต็อก
        if stock_map.get(category.id, 0) < required_stock:
            flash(f"สินค้า {category.name} มีสต็อกไม่เพียงพอ", "error")
            return redirect(url_for('idgen'))
        
        # 3. ตรวจสอบยอดเงิน
        if user.balance < total_price:
            flash(f"ยอดเงินไม่พอ: คุณมี {user.balance:.2f} บาท แต่ต้องใช้ {total_price:.2f} บาท", "error")
            return redirect(url_for('idgen'))
        
        # --- เริ่มทำรายการ ---
        try:
            # 4. ดึงสินค้า
            stocks_to_sell = Stock.query.filter_by(category_id=cat_id, is_sold=False).limit(required_stock).all()
            
            purchased_data = ""
            for stock in stocks_to_sell:
                stock.is_sold = True
                purchased_data += stock.content + "\n"
                db.session.add(stock)
                
            # 5. หักยอดเงิน
            user.balance -= total_price
            
            # 6. สร้างประวัติการสั่งซื้อ
            new_order = Order(
                user_id=user.id, 
                category_name=category.name,
                price=total_price,
                data=purchased_data.strip()
            )
            db.session.add(new_order)
            
            db.session.commit()
            
            flash(f"ซื้อสินค้า {category.name} จำนวน {qty} ชิ้น สำเร็จ! หักเงิน {total_price:.2f} บาท", "success")
            return redirect(url_for('history'))

        except Exception as e:
            db.session.rollback()
            flash("เกิดข้อผิดพลาดในการทำรายการ กรุณาลองใหม่", "error")
            print(f"ERROR on purchase: {e}")
            return redirect(url_for('idgen'))

    return render_template('idgen.html', categories=categories, stock_map=stock_map)

@app.route('/history')
@login_required
def history():
    user = User.query.get(session['user_id'])
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    topups = TopupHistory.query.filter_by(user_id=user.id).order_by(TopupHistory.created_at.desc()).all()
    
    return render_template('history.html', orders=orders, topups=topups)


@app.route('/topup', methods=['GET', 'POST'])
@login_required
def topup():
    conf = get_config()
    if not conf.truemoney_phone:
        flash("ยังไม่ได้ตั้งค่าเบอร์ TrueMoney ในหน้า Admin", "error")
        return redirect(url_for('home'))

    if request.method == 'POST':
        voucher_url = request.form.get('voucher_url')
        user = User.query.get(session['user_id'])
        
        if not voucher_url:
            flash("กรุณาใส่ลิงก์ซองอั่งเปา", "error")
            return redirect(url_for('topup'))

        # ตรวจสอบว่าลิงก์เคยถูกใช้แล้วหรือไม่ (โดยใช้โค้ดอ้างอิงของซอง)
        wallet_api = TrueMoneyWallet(conf.truemoney_phone)
        voucher_code = wallet_api.extract_voucher_code(voucher_url)
        
        if TopupHistory.query.filter_by(ref=voucher_code, status='success').first():
             flash("ลิงก์ซองนี้เคยถูกใช้งานสำเร็จไปแล้ว", "error")
             return redirect(url_for('topup'))
        
        # --- เริ่มทำรายการเติมเงิน ---
        try:
            # สร้างรายการรอตรวจสอบก่อน
            pending_topup = TopupHistory(
                user_id=user.id,
                amount=0.0,
                method='truemoney_gift',
                status='pending',
                ref=voucher_code
            )
            db.session.add(pending_topup)
            db.session.commit()
            
            # ดึงเงินจาก TrueMoney API
            result = wallet_api.redeem_voucher(voucher_url)
            
            if result['success']:
                amount = result['amount']
                
                # อัปเดตยอดเงินผู้ใช้
                user.balance += amount
                
                # อัปเดตสถานะ Topup History
                pending_topup.amount = amount
                pending_topup.status = 'success'
                
                db.session.commit()
                flash(f"เติมเงินสำเร็จ! ได้รับเงิน {amount:.2f} บาท", "success")
                
            else:
                # ถ้าไม่สำเร็จ
                pending_topup.status = 'failed'
                db.session.commit()
                flash(f"เติมเงินไม่สำเร็จ: {result['message']}", "error")

        except Exception as e:
            db.session.rollback()
            flash("เกิดข้อผิดพลาดกับระบบ กรุณาลองใหม่ในภายหลัง", "error")
            print(f"TrueMoney API ERROR: {e}")
            
        return redirect(url_for('topup'))

    return render_template('topup.html')


# --- Admin Routes ---
@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin_panel():
    conf = get_config()
    
    # จัดการ POST requests จากฟอร์มต่างๆ
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'update_config':
                conf.site_name = request.form.get('site_name')
                conf.logo_url = request.form.get('logo_url')
                conf.announcement = request.form.get('announcement')
                conf.contact_url = request.form.get('contact_url')
                conf.truemoney_phone = request.form.get('truemoney_phone')
                db.session.commit()
                flash("ตั้งค่าเว็บไซต์สำเร็จ", "success")
                
            elif action == 'add_category':
                name = request.form.get('name')
                price = float(request.form.get('price'))
                image_url = request.form.get('image_url')
                description = request.form.get('description')
                
                new_cat = Category(name=name, price=price, image_url=image_url, description=description)
                db.session.add(new_cat)
                db.session.commit()
                flash("เพิ่มหมวดหมู่สำเร็จ", "success")

            elif action == 'delete_category':
                cat_id = request.form.get('category_id')
                if Stock.query.filter_by(category_id=cat_id, is_sold=False).count() == 0:
                    Category.query.filter_by(id=cat_id).delete()
                    db.session.commit()
                    flash("ลบแล้ว", "success")
                else:
                    flash("ลบไม่ได้ มีสินค้าเหลืออยู่", "error")
                    
            elif action == 'add_stock':
                lines = request.form.get('data').strip().split('\n')
                cat_id = request.form.get('category_id')
                for line in lines:
                    if line.strip():
                        db.session.add(Stock(category_id=cat_id, content=line.strip()))
                db.session.commit()
                flash(f"เติมสต็อก {len(lines)} ชิ้น", "success")

            elif action == 'add_banner':
                url = request.form.get('url')
                new_banner = Banner(url=url)
                db.session.add(new_banner)
                db.session.commit()
                flash("เพิ่มแบนเนอร์แล้ว", "success")

            elif action == 'delete_banner':
                Banner.query.filter_by(id=request.form.get('banner_id')).delete()
                db.session.commit()
                flash("ลบแบนเนอร์แล้ว", "success")
            
            elif action == 'approve_topup':
                topup_id = request.form.get('topup_id')
                t = TopupHistory.query.get(topup_id)
                if t and t.status == 'pending':
                    # ในระบบนี้เราใช้ auto topup เลยไม่มี pending จริงจัง แต่ถ้ามีไว้รองรับช่องทางอื่น
                    # สามารถเพิ่ม logic อนุมัติตรงนี้ได้
                    t.status = 'success'
                    t.user.balance += t.amount
                    db.session.commit()
                    flash("อนุมัติการเติมเงินแล้ว", "success")
                else:
                    flash("ไม่พบรายการหรือรายการนี้ถูกดำเนินการแล้ว", "error")

        except Exception as e:
            db.session.rollback()
            flash(f"เกิดข้อผิดพลาด: {e}", "error")

        return redirect(url_for('admin_panel'))


    # ดึงข้อมูลสำหรับ Admin Dashboard
    categories = Category.query.all()
    banners = Banner.query.order_by(Banner.order).all()
    all_users = User.query.order_by(User.id.desc()).all()
    pending_topups = TopupHistory.query.filter_by(status='pending').all()
    
    # คำนวณสต็อก
    stock_counts = db.session.query(Stock.category_id, db.func.count(Stock.id)).filter(Stock.is_sold == False).group_by(Stock.category_id).all()
    stock_info = {cat_id: count for cat_id, count in stock_counts}

    # สถิติ
    stats = {
        'total_users': User.query.count(),
        'total_topup': db.session.query(db.func.sum(TopupHistory.amount)).filter_by(status='success').scalar() or 0,
        'total_revenue': db.session.query(db.func.sum(Order.price)).scalar() or 0,
        'total_orders_count': Order.query.count(),
        'total_stock_left': Stock.query.filter_by(is_sold=False).count()
    }

    return render_template('admin.html', config=conf, categories=categories, stock_info=stock_info, banners=banners, all_users=all_users, pending_topups=pending_topups, stats=stats)

def ensure_admin_exists():
    """ฟังก์ชันเช็คและสร้างแอดมินตามที่ระบุในโค้ด"""
    with app.app_context():
        admin = User.query.filter_by(username=ADMIN_USERNAME).first()
        if not admin:
            print(f"🔥 Creating Admin: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
            new_admin = User(
                username=ADMIN_USERNAME,
                password=generate_password_hash(ADMIN_PASSWORD),
                role='admin',
                balance=999.0
            )
            db.session.add(new_admin)
            db.session.commit()
        else:
            # อัปเดตรหัสผ่านให้ตรงกับในโค้ดเสมอ (เผื่อแก้ในโค้ดแล้วอยากให้เปลี่ยนตาม)
            admin.password = generate_password_hash(ADMIN_PASSWORD)
            db.session.commit()

@app.cli.command("init-db")
def init_db_command():
    """สร้างตารางฐานข้อมูลและสร้างแอดมินเริ่มต้น"""
    with app.app_context():
        db.create_all()
        ensure_admin_exists()
        print("Database initialized and Admin created!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_admin_exists()
    app.run(debug=True)