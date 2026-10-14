
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
            keyword = f"%{search}%"
            member_list = connection.execute(
                """
                SELECT * FROM members
                WHERE member_code LIKE ?
                   OR name LIKE ?
                   OR COALESCE(email, '') LIKE ?
                   OR COALESCE(phone, '') LIKE ?
                ORDER BY id DESC
                """,
                (keyword, keyword, keyword, keyword),
            ).fetchall()
        else:
            member_list = connection.execute(
                "SELECT * FROM members ORDER BY id DESC"
            ).fetchall()

        total_members = connection.execute(
            "SELECT COUNT(*) FROM members"
        ).fetchone()[0]

        return render_template(
            "members.html",
            members=member_list,
            search=search,
            total_members=total_members,
        )
    finally:
        connection.close()


@app.route("/members/add", methods=["POST"])
def add_member():
    member_code = request.form.get("member_code", "").strip()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip() or None
    phone = request.form.get("phone", "").strip() or None

    if not member_code or not name:
        flash("กรุณากรอกรหัสสมาชิกและชื่อสมาชิก", "error")
        return redirect(url_for("members"))

    connection = get_db_connection()

    try:
        connection.execute(
            """
            INSERT INTO members (member_code, name, email, phone)
            VALUES (?, ?, ?, ?)
            """,
            (member_code, name, email, phone),
        )
        connection.commit()
        flash("เพิ่มสมาชิกสำเร็จ", "success")
    except Exception as error:
        connection.rollback()
        if "UNIQUE constraint failed" in str(error):
            flash("รหัสสมาชิกหรืออีเมลนี้มีอยู่ในระบบแล้ว", "error")
        else:
            flash("ไม่สามารถเพิ่มสมาชิกได้ กรุณาตรวจสอบข้อมูล", "error")
    finally:
        connection.close()

    return redirect(url_for("members"))


@app.route("/members/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    connection = get_db_connection()

    try:
        member = connection.execute(
            "SELECT * FROM members WHERE id = ?",
            (member_id,),
        ).fetchone()

        if member is None:
            flash("ไม่พบสมาชิกที่ต้องการแก้ไข", "error")
            return redirect(url_for("members"))

        if request.method == "POST":
            member_code = request.form.get("member_code", "").strip()
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip() or None
            phone = request.form.get("phone", "").strip() or None

            if not member_code or not name:
                flash("กรุณากรอกรหัสสมาชิกและชื่อสมาชิก", "error")
                return redirect(url_for("edit_member", member_id=member_id))

            try:
                connection.execute(
                    """
                    UPDATE members
                    SET member_code = ?, name = ?, email = ?, phone = ?
                    WHERE id = ?
                    """,
                    (member_code, name, email, phone, member_id),
                )
                connection.commit()
                flash("แก้ไขข้อมูลสมาชิกสำเร็จ", "success")
                return redirect(url_for("members"))
            except Exception:
                connection.rollback()
                flash("รหัสสมาชิกหรืออีเมลนี้อาจมีอยู่ในระบบแล้ว", "error")
                return redirect(url_for("edit_member", member_id=member_id))

        return render_template("edit_member.html", member=member)
    finally:
        connection.close()


@app.route("/members/delete/<int:member_id>", methods=["POST"])
def delete_member(member_id):
    connection = get_db_connection()

    try:
        member = connection.execute(
            "SELECT id FROM members WHERE id = ?",
            (member_id,),
        ).fetchone()

        if member is None:
            flash("ไม่พบสมาชิกที่ต้องการลบ", "error")
            return redirect(url_for("members"))

        history = connection.execute(
            "SELECT COUNT(*) FROM borrow_records WHERE member_id = ?",
            (member_id,),
        ).fetchone()[0]

        if history > 0:
            flash("ไม่สามารถลบสมาชิกที่มีประวัติการยืมหนังสือได้", "error")
            return redirect(url_for("members"))

        connection.execute(
            "DELETE FROM members WHERE id = ?",
            (member_id,),
        )
        connection.commit()
        flash("ลบสมาชิกสำเร็จ", "success")
    except Exception:
        connection.rollback()
        flash("ไม่สามารถลบสมาชิกได้", "error")
    finally:
        connection.close()

    return redirect(url_for("members"))


@app.route("/loans")
def loans():
    search = request.args.get("search", "").strip()
    connection = get_db_connection()

    try:
        sql = """
            SELECT
                br.id,
                br.borrow_date,
                br.due_date,
                br.return_date,
                br.fine,
                br.status,
                b.title AS book_title,
                b.author AS book_author,
                m.member_code,
                m.name AS member_name,
                CASE
                    WHEN br.status = 'borrowed'
                         AND date('now', 'localtime') > br.due_date
                    THEN CAST(
                        julianday(date('now', 'localtime'))
                        - julianday(br.due_date) AS INTEGER
                    ) * 5
                    ELSE br.fine
                END AS current_fine
            FROM borrow_records br
            JOIN books b ON b.id = br.book_id
            JOIN members m ON m.id = br.member_id
        """
        params = []

        if search:
            keyword = f"%{search}%"
            sql += """
                WHERE b.title LIKE ?
                   OR b.author LIKE ?
                   OR m.member_code LIKE ?
                   OR m.name LIKE ?
            """
            params = [keyword, keyword, keyword, keyword]

        sql += """
            ORDER BY
                CASE WHEN br.status = 'borrowed' THEN 0 ELSE 1 END,
                br.id DESC
        """

        records = connection.execute(sql, params).fetchall()

        books = connection.execute(
            """
            SELECT
                b.id,
                b.title,
                b.author,
                b.total_copies - (
                    SELECT COUNT(*)
                    FROM borrow_records br
                    WHERE br.book_id = b.id
                      AND br.status = 'borrowed'
                ) AS available_copies
            FROM books b
            ORDER BY b.title
            """
        ).fetchall()

        members_list = connection.execute(
            "SELECT id, member_code, name FROM members ORDER BY name"
        ).fetchall()

        active_loans = connection.execute(
            "SELECT COUNT(*) FROM borrow_records WHERE status = 'borrowed'"
        ).fetchone()[0]

        overdue_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM borrow_records
            WHERE status = 'borrowed'
              AND due_date < date('now', 'localtime')
            """
        ).fetchone()[0]

        return render_template(
            "loans.html",
            records=records,
            books=books,
            members=members_list,
            search=search,
            active_loans=active_loans,
            overdue_count=overdue_count,
            today=date.today().isoformat(),
        )
    finally:
        connection.close()


@app.route("/loans/borrow", methods=["POST"])
def borrow_book():
    book_id = request.form.get("book_id", type=int)
    member_id = request.form.get("member_id", type=int)

    if not book_id or not member_id:
        flash("กรุณาเลือกหนังสือและสมาชิก", "error")
        return redirect(url_for("loans"))

    connection = get_db_connection()

    try:
        book = connection.execute(
            """
            SELECT
                b.id,
                b.total_copies - (
                    SELECT COUNT(*)
                    FROM borrow_records br
                    WHERE br.book_id = b.id
                      AND br.status = 'borrowed'
                ) AS available_copies
            FROM books b
            WHERE b.id = ?
            """,
            (book_id,),
        ).fetchone()

        member = connection.execute(
            "SELECT id FROM members WHERE id = ?",
            (member_id,),
        ).fetchone()

        if book is None or member is None:
            flash("ไม่พบหนังสือหรือสมาชิกที่เลือก", "error")
            return redirect(url_for("loans"))

        if book["available_copies"] <= 0:
            flash("หนังสือเล่มนี้ไม่มีสำเนาว่างให้ยืม", "error")
            return redirect(url_for("loans"))

        active_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM borrow_records
            WHERE member_id = ? AND status = 'borrowed'
            """,
            (member_id,),
        ).fetchone()[0]

        if active_count >= 3:
            flash("สมาชิกคนนี้ยืมหนังสือค้างอยู่ครบ 3 รายการแล้ว", "error")
            return redirect(url_for("loans"))

        borrow_date = date.today()
        due_date = borrow_date + timedelta(days=7)

        connection.execute(
            """
            INSERT INTO borrow_records
                (book_id, member_id, borrow_date, due_date, status, fine)
            VALUES (?, ?, ?, ?, 'borrowed', 0)
            """,
            (
                book_id,
                member_id,
                borrow_date.isoformat(),
                due_date.isoformat(),
            ),
        )

        connection.commit()
        flash(
            f"ยืมหนังสือสำเร็จ กำหนดคืนวันที่ {due_date.strftime('%d/%m/%Y')}",
            "success",
        )
    except Exception:
        connection.rollback()
        flash("ไม่สามารถทำรายการยืมได้ กรุณาลองใหม่", "error")
    finally:
        connection.close()

    return redirect(url_for("loans"))


@app.route("/loans/return/<int:loan_id>", methods=["POST"])
def return_book(loan_id):
    connection = get_db_connection()

    try:
        record = connection.execute(
            """
            SELECT id, due_date, status
            FROM borrow_records
            WHERE id = ?
            """,
            (loan_id,),
        ).fetchone()

        if record is None:
            flash("ไม่พบรายการยืมหนังสือ", "error")
            return redirect(url_for("loans"))

        if record["status"] == "returned":
            flash("รายการนี้คืนหนังสือแล้ว", "error")
            return redirect(url_for("loans"))

        return_date = date.today()
        due_date = date.fromisoformat(record["due_date"])
        overdue_days = max((return_date - due_date).days, 0)
        fine = overdue_days * 5

        connection.execute(
            """
            UPDATE borrow_records
            SET return_date = ?, status = 'returned', fine = ?
            WHERE id = ?
            """,
            (return_date.isoformat(), fine, loan_id),
        )

        connection.commit()

        if fine > 0:
            flash(
                f"คืนหนังสือสำเร็จ ล่าช้า {overdue_days} วัน ค่าปรับ {fine} บาท",
                "success",
            )
        else:
            flash("คืนหนังสือสำเร็จ ไม่มีค่าปรับ", "success")
    except Exception:
        connection.rollback()
        flash("ไม่สามารถคืนหนังสือได้ กรุณาลองใหม่", "error")
    finally:
        connection.close()

    return redirect(url_for("loans"))


if __name__ == "__main__":
    app.run(debug=True)
