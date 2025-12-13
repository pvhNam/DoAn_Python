from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from models.user import create_user, verify_user

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user_data = verify_user(request.form["username"], request.form["password"])
        if user_data:
            # Import User ở đây để tránh circular import nếu cần, hoặc dùng từ models
            from models.user import User 
            user_obj = User(user_data["id"], user_data["username"], user_data["balance"])
            login_user(user_obj)
            return redirect(url_for("market.market"))
        flash("Sai tài khoản hoặc mật khẩu", "danger")
    return render_template("login.html")

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if create_user(username, password):
            flash("Đăng ký thành công! Đăng nhập ngay", "success")
            return redirect(url_for("auth.login"))
        flash("Tên đăng nhập đã tồn tại", "danger")
    return render_template("register.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))