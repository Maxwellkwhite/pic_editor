from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, PasswordField
from wtforms.validators import DataRequired, Email, Length
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Date, Time, JSON, Boolean
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import random
import stripe
import os
import smtplib
import json
from flask_ckeditor import CKEditorField
from datetime import date, time
import datetime
import os
from openai import OpenAI
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


APP_NAME = 'Studyvant'
stripe.api_key = os.environ.get('STRIPE_API')


app = Flask(__name__)
ckeditor = CKEditor(app)
Bootstrap5(app)
app.config['SECRET_KEY'] = '1afjdlkafjd'

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)

class Base(DeclarativeBase):
    pass

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI", 'sqlite:///users.db')
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Create a form to register new users
class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired() ])
    password = PasswordField("Password", validators=[DataRequired()])
    name = StringField("Name", validators=[DataRequired()])
    submit = SubmitField("Sign Me Up!")

# Create a form to login existing users
class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Let Me In!")

class ChangePassword(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired()])
    submit = SubmitField("Change Password")

class Feedback_Form(FlaskForm):
    title = StringField("Short Title", validators=[DataRequired()])
    feedback = StringField("Feedback", validators=[DataRequired()])
    submit = SubmitField("Provide Feedback")

#user DB
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    premium_level: Mapped[int] = mapped_column(Integer)
    date_of_signup: Mapped[Date] = mapped_column(Date)
    time_of_signup: Mapped[Time] = mapped_column(Time)
    end_date_premium: Mapped[Date] = mapped_column(Date)
    points: Mapped[int] = mapped_column(Integer)
    picture_count: Mapped[int] = mapped_column(Integer)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token: Mapped[str] = mapped_column(String(100), nullable=True)

class Picture(db.Model):
    __tablename__ = "pictures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    picture_json: Mapped[str] = mapped_column(JSON())
    title: Mapped[str] = mapped_column(String())
    class_name: Mapped[str] = mapped_column(String(250), unique=False, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer)
    best_score: Mapped[int] = mapped_column(Integer)

class ClassList(db.Model):
    __tablename__ = "class_list"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    class_name: Mapped[str] = mapped_column(String(250), unique=False, nullable=False)

# Add new association table for upvotes
class FeedbackUpvote(db.Model):
    __tablename__ = "feedback_upvotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    feedback_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("feedback.id"))

# Update Feedback class to include relationship
class Feedback(db.Model):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(50))
    feedback: Mapped[str] = mapped_column(String())
    upvote_count: Mapped[int] = mapped_column(Integer)
    # Add relationship to track upvoters
    upvoters = relationship('User', secondary='feedback_upvotes', backref='upvoted_feedback')

with app.app_context():
    db.create_all()

@app.route('/', methods=["GET", "POST"])
def home_page():
    return render_template("index.html")

@app.route('/picture', methods=["GET", "POST"])
def picture():
    return render_template("picture.html")

@app.route('/price-page', methods=["GET", "POST"])
def price_page():
    return render_template("price_page.html")


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            # Check if user email is already present in the database.
            result = db.session.execute(db.select(User).where(User.email == form.email.data.lower()))
            user = result.scalar()
            if user:
                flash("You've already signed up with that email, log in instead!")
                return redirect(url_for('login'))

            # Generate verification token
            verification_token = secrets.token_urlsafe(32)
            
            hash_and_salted_password = generate_password_hash(
                form.password.data,
                method='pbkdf2:sha256',
                salt_length=8
            )
            new_user = User(
                email=form.email.data.lower(),
                name=form.name.data,
                password=hash_and_salted_password,
                date_of_signup=datetime.date.today(),
                end_date_premium=datetime.date.today(),
                premium_level=0,
                points=0,
                picture_count=1,
                verified=False,
                verification_token=verification_token
            )
            
            # Send verification email before committing to database
            if send_verification_email(form.email.data.lower(), verification_token):
                db.session.add(new_user)
                db.session.commit()
                flash("Please check your email to verify your account before logging in. If you don't see the email, please check your spam folder. Email will come from mwdynamics@gmail.com")
                return redirect(url_for("login"))
            else:
                return redirect(url_for("register"))
                
        except Exception as e:
            print(f"Registration error: {str(e)}")
            flash("An error occurred during registration. Please try again.")
            return redirect(url_for("register"))
            
    return render_template("register.html", form=form, current_user=current_user)

@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        password = form.password.data
        result = db.session.execute(db.select(User).where(User.email == form.email.data.lower()))
        user = result.scalar()
        
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.')
            return redirect(url_for('login'))
        elif not user.verified:
            flash('Please verify your email before logging in.')
            return redirect(url_for('login'))
        else:
            login_user(user)
            if user.picture_count == 0:
                return redirect(url_for('price_page'))
            else:
                return redirect(url_for('picture_selector'))

    return render_template("login.html", form=form, current_user=current_user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home_page'))

#for test of Stripe
YOUR_DOMAIN = 'http://127.0.0.1:5002'
#for live of Stripe
DOMAIN2 = 'https://studyvant.com'

@app.route('/create-checkout-session', methods=['POST', 'GET'])
def create_checkout_session():
    plan = request.args.get('plan')
    try:
        if plan == '10':
            price = 499  # $4.99
            product_name = '10 picturezes'
        elif plan == '25':
            price = 999  # $9.99
            product_name = '25 picturezes'
        elif plan == '100':
            price = 2499  # $24.99
            product_name = '100 picturezes'
        else:
            return "Invalid plan selected", 400
        # stripe.Coupon.create(
        # id="free-test",
        # percent_off=100,
        # )
        # stripe.PromotionCode.create(
        # coupon="free-test",
        # code="FREETEST",
        # )
        checkout_session = stripe.checkout.Session.create(
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': product_name,
                    },
                    'unit_amount': price,
                },
                'quantity': 1,
            }],
            mode='payment',
            allow_promotion_codes=True,
            success_url=YOUR_DOMAIN + f'/success?plan={plan}',
            cancel_url=YOUR_DOMAIN + '/cancel',
        )
    except Exception as e:
        return str(e)
    return redirect(checkout_session.url, code=303)

@app.route('/cancel', methods=['POST', 'GET'])
def cancel_session():
    return redirect(url_for('price_page'))

@app.route('/success', methods=['POST', 'GET'])
def success_session():
    with app.app_context():
        plan = request.args.get('plan')
        g_user = current_user.get_id()
        completed_update = db.session.execute(db.select(User).where(User.id == g_user)).scalar()
        completed_update.picture_count = completed_update.picture_count + int(plan)
        db.session.commit()
    return redirect(url_for('picture_selector'))

@app.route('/privacy-policy', methods=['POST', 'GET'])
def privacy_policy():
    return render_template("privacy_policy.html")

@app.route('/terms-and-conditions', methods=['POST', 'GET'])
def terms_and_conditions():
    return render_template("terms_and_conditions.html")

@app.route('/change-password', methods=["GET", "POST"])
def change_password():
    form = ChangePassword()
    g_user = current_user.get_id()
    if form.validate_on_submit():
        password = form.password.data
        new_password = form.new_password.data
        result = db.session.execute(db.select(User).where(User.email == form.email.data.lower()))
        # Note, email in db is unique so will only have one result.
        user = result.scalar()
        # Email doesn't exist
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('change_password'))
        # Password incorrect
        elif not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.')
            return redirect(url_for('change_password'))
        else:
            completed_update = db.session.execute(db.select(User).where(User.id == g_user)).scalar()
            completed_update.password = generate_password_hash(
                    new_password,
                    method='pbkdf2:sha256',
                    salt_length=8)
            db.session.commit()
            flash('Password Changed')
            return redirect(url_for('change_password'))

    return render_template("change_password.html", form=form, current_user=current_user)

@app.route('/feedback', methods=['POST', 'GET'])
def feedback():
    form=Feedback_Form()
    if form.validate_on_submit():
        new_feedback = Feedback(
            user_id=current_user.id,
            title=form.title.data,
            feedback=form.feedback.data,
            upvote_count=0,
        )
        db.session.add(new_feedback)
        db.session.commit()
        flash('Feedback submitted! Thank you for taking the time to help.')
    feedback_list = Feedback.query.all()
    # Get list of feedback IDs user has upvoted
    upvoted_feedback_ids = []
    if current_user.is_authenticated:
        upvoted_feedback_ids = [f.id for f in current_user.upvoted_feedback]
    return render_template("feedback.html", form=form, feedback_list=feedback_list, upvoted_feedback_ids=upvoted_feedback_ids)

@app.route('/delete-feedback/<feedback_id>', methods=['POST'])
def delete_feedback(feedback_id):
    feedback = Feedback.query.get_or_404(feedback_id)
    db.session.delete(feedback)
    db.session.commit()
    return jsonify({'success': True})

# Add new route to handle upvotes
@app.route('/upvote/<int:feedback_id>', methods=['POST'])
def upvote_feedback(feedback_id):
    if not current_user.is_authenticated:
        return jsonify({'error': 'Must be logged in to upvote'}), 401
        
    feedback = Feedback.query.get_or_404(feedback_id)
    
    # Check if user already upvoted
    existing_upvote = FeedbackUpvote.query.filter_by(
        user_id=current_user.id,
        feedback_id=feedback_id
    ).first()
    
    if existing_upvote:
        # Remove upvote if already voted
        db.session.delete(existing_upvote)
        feedback.upvote_count -= 1
    else:
        # Add new upvote
        new_upvote = FeedbackUpvote(user_id=current_user.id, feedback_id=feedback_id)
        db.session.add(new_upvote)
        feedback.upvote_count += 1
    
    db.session.commit()
    return jsonify({'upvote_count': feedback.upvote_count})

def send_verification_email(email, token):
    try:
        sender_email = os.environ.get('EMAIL_ADDRESS')
        sender_password = os.environ.get('EMAIL_PASSWORD')
        
        if not sender_email or not sender_password:
            print("Email credentials not found in environment variables")
            flash("Error sending verification email. Please contact support.")
            return False
        
        # Create MIME message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = email
        msg['Subject'] = f"Verify Your {APP_NAME} Account"
        
        # Create HTML body
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background-color: #f8f9fa; padding: 20px; text-align: center;">
                    <h1 style="color: #333;">Welcome to {APP_NAME}!</h1>
                </div>
                <div style="padding: 20px;">
                    <p>Thank you for registering! Please verify your email address to complete your account setup.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{DOMAIN2}/verify/{token}" 
                           style="background-color: #007bff; color: white; padding: 12px 25px; 
                                  text-decoration: none; border-radius: 5px;">
                            Verify Email
                        </a>
                    </div>
                    <p style="color: #666; font-size: 0.9em;">
                        If the button doesn't work, copy and paste this link into your browser:<br>
                        {DOMAIN2}/verify/{token}
                    </p>
                </div>
            </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html'))
        
        # Send email
        with smtplib.SMTP("smtp.gmail.com", port=587) as connection:
            connection.starttls()
            try:
                connection.login(user=sender_email, password=sender_password)
                connection.send_message(msg)
                return True
            except smtplib.SMTPAuthenticationError:
                print("Failed to authenticate with Gmail")
                flash("Error sending verification email. Please contact support.")
                return False
                
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        flash("Error sending verification email. Please contact support.")
        return False

@app.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if user:
        user.verified = True
        user.verification_token = None  # Clear the token after use
        db.session.commit()
        flash("Your email has been verified! You can now log in.")
    else:
        flash("Invalid verification token.")
    return redirect(url_for('login'))

@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    email = request.form.get('email')
    if not email:
        flash("Please enter your email address first.")
        return redirect(url_for('login'))
        
    user = User.query.filter_by(email=email.lower()).first()
    if not user:
        flash("No account found with that email address.")
        return redirect(url_for('login'))
        
    if user.verified:
        flash("This email is already verified.")
        return redirect(url_for('login'))
        
    # Generate new verification token
    new_token = secrets.token_urlsafe(32)
    user.verification_token = new_token
    db.session.commit()
    
    if send_verification_email(email, new_token):
        flash("Verification email has been resent. Please check your inbox and spam folder. Email will come from mwdynamics@gmail.com")
    else:
        flash("Error sending verification email. Please try again or contact support.")
    
    return redirect(url_for('login'))

@app.route('/user-dashboard', methods=['POST', 'GET'])
def user_dashboard():
    # Get today's date
    today = datetime.date.today()
    three_days_ago = today - datetime.timedelta(days=3)
    
    # Query users who signed up in the last 3 days
    new_users = User.query.filter(
        User.date_of_signup >= three_days_ago
    ).all()
    # Get current user
    current_user_data = User.query.filter_by(id=current_user.id).first()
    return render_template("user_dashboard.html", new_users=new_users, current_user_data=current_user_data)

@app.route('/education-resources', methods=['POST', 'GET'])
def education_resources():
    return render_template("education_resources.html")

if __name__ == "__main__":
    app.run(debug=True, port=5002)




