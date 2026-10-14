import os
from datetime import date, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash
from database.db import get_db_connection, init_db

app = Flask(__name__)
app.secret_key = "bookflow-local-development-key"

init_db()


@app.route("/")
def home():
    search = request.args.get("search", "").strip()
    connection = get_db_connection()

    try:
        sql = """
            SELECT
                b.*,
                b.total_copies - (
                    SELECT COUNT(*)
                    FROM borrow_records br
                    WHERE br.book_id = b.id
                      AND br.status = 'borrowed'
                ) AS available_copies
            FROM books b
        """
        params = []

        if search:
            keyword = f"%{search}%"
            sql += """
                WHERE b.title LIKE ?
                   OR b.author LIKE ?
                   OR COALESCE(b.isbn, '') LIKE ?
                   OR COALESCE(b.category, '') LIKE ?
            """
            params = [keyword, keyword, keyword, keyword]

        sql += " ORDER BY b.id DESC"
        books = connection.execute(sql, params).fetchall()

        total_books = connection.execute(
            "SELECT COUNT(*) FROM books"
        ).fetchone()[0]

        total_members = connection.execute(
            "SELECT COUNT(*) FROM members"
        ).fetchone()[0]

        active_loans = connection.execute(
            "SELECT COUNT(*) FROM borrow_records WHERE status = 'borrowed'"
        ).fetchone()[0]

        return render_template(
            "index.html",
            books=books,
            search=search,
            total_books=total_books,
            total_members=total_members,
            active_loans=active_loans,
        )
    finally:
        connection.close()


@app.route("/books/add", methods=["POST"])
def add_book():
    isbn = request.form.get("isbn", "").strip() or None
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    category = request.form.get("category", "").strip() or None

    try:
        total_copies = int(request.form.get("total_copies", "1"))
        if total_copies < 1:
            raise ValueError
    except ValueError:
        flash("จำนวนหนังสือต้องเป็นจำนวนเต็มตั้งแต่ 1 เล่มขึ้นไป", "error")
        return redirect(url_for("home"))

    if not title or not author:
        flash("กรุณากรอกชื่อหนังสือและชื่อผู้แต่ง", "error")
        return redirect(url_for("home"))

    connection = get_db_connection()

    try:
        connection.execute(
            """
            INSERT INTO books (isbn, title, author, category, total_copies)
            VALUES (?, ?, ?, ?, ?)
            """,
            (isbn, title, author, category, total_copies),
        )
        connection.commit()
        flash("เพิ่มหนังสือสำเร็จ", "success")
    except Exception as error:
        connection.rollback()
        if "UNIQUE constraint failed: books.isbn" in str(error):
            flash("ISBN นี้มีอยู่ในระบบแล้ว", "error")
        else:
            flash("ไม่สามารถเพิ่มหนังสือได้ กรุณาตรวจสอบข้อมูล", "error")
    finally:
        connection.close()

    return redirect(url_for("home"))


@app.route("/books/edit/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    connection = get_db_connection()

    try:
        book = connection.execute(
            "SELECT * FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()

        if book is None:
            flash("ไม่พบหนังสือที่ต้องการแก้ไข", "error")
            return redirect(url_for("home"))

        if request.method == "POST":
            isbn = request.form.get("isbn", "").strip() or None
            title = request.form.get("title", "").strip()
            author = request.form.get("author", "").strip()
            category = request.form.get("category", "").strip() or None

            try:
                total_copies = int(request.form.get("total_copies", "1"))
                borrowed_copies = connection.execute(
                    """
                    SELECT COUNT(*) FROM borrow_records
                    WHERE book_id = ? AND status = 'borrowed'
                    """,
                    (book_id,),
                ).fetchone()[0]

                if total_copies < 1 or total_copies < borrowed_copies:
                    raise ValueError
            except ValueError:
                flash(
                    "จำนวนหนังสือต้องไม่น้อยกว่า 1 และต้องไม่น้อยกว่าจำนวนที่กำลังถูกยืม",
                    "error",
                )
                return redirect(url_for("edit_book", book_id=book_id))

            if not title or not author:
                flash("กรุณากรอกชื่อหนังสือและชื่อผู้แต่ง", "error")
                return redirect(url_for("edit_book", book_id=book_id))

            try:
                connection.execute(
                    """
                    UPDATE books
                    SET isbn = ?, title = ?, author = ?,
                        category = ?, total_copies = ?
                    WHERE id = ?
                    """,
                    (isbn, title, author, category, total_copies, book_id),
                )
                connection.commit()
                flash("แก้ไขข้อมูลหนังสือสำเร็จ", "success")
                return redirect(url_for("home"))
            except Exception:
                connection.rollback()
                flash("ISBN นี้อาจมีอยู่ในระบบแล้ว กรุณาตรวจสอบ", "error")
                return redirect(url_for("edit_book", book_id=book_id))

        return render_template("edit_book.html", book=book)
    finally:
        connection.close()


@app.route("/books/delete/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    connection = get_db_connection()

    try:
        borrowed = connection.execute(
            """
            SELECT COUNT(*) FROM borrow_records
            WHERE book_id = ? AND status = 'borrowed'
            """,
            (book_id,),
        ).fetchone()[0]

        history = connection.execute(
            "SELECT COUNT(*) FROM borrow_records WHERE book_id = ?",
            (book_id,),
        ).fetchone()[0]

        if borrowed > 0:
            flash("ไม่สามารถลบหนังสือที่ยังมีรายการยืมค้างอยู่", "error")
        elif history > 0:
            flash("ไม่สามารถลบหนังสือที่มีประวัติการยืม กรุณาเก็บไว้เป็นประวัติ", "error")
        else:
            connection.execute(
                "DELETE FROM books WHERE id = ?",
                (book_id,),
            )
            connection.commit()
            flash("ลบหนังสือสำเร็จ", "success")
    except Exception:
        connection.rollback()
        flash("ไม่สามารถลบหนังสือได้", "error")
    finally:
        connection.close()

    return redirect(url_for("home"))


@app.route("/members")
def members():
    search = request.args.get("search", "").strip()
    connection = get_db_connection()

    try:
        if search:
            keyword = f"%
