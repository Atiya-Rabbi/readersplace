import os
import json
import requests
from flask import Flask, session, render_template, request, redirect, jsonify
from flask_session import Session
from helpers import login_required
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

@app.route("/signup", methods=["GET","POST"])
def signup():
	session.clear()
	if request.method=="POST":
		password = request.form.get("password")
		repassword = request.form.get("repassword")
		if(password!=repassword):
			return render_template("error.html", message="Passwords do not match!")

		#hash password
		pw_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
		
		fullname = request.form.get("fullname")
		username = request.form.get("username")

		#check if username exist in databse
		if db.execute("SELECT username FROM users WHERE username=:username", {"username": username}).rowcount != 0:
			return render_template("error.html", message="Username already exists!")

		question = request.form.get("question")
		answer = request.form.get("answer")

		#store in database
		db.execute("INSERT INTO users (fullname, username, password, question, answer) VALUES (:fullname, :username, :password, :question, :answer)",
	            {"fullname": fullname, "username": username, "password": pw_hash, "question": question, "answer": answer})
		db.commit()

		return render_template("login.html", msg="Account created!")
	return render_template("signup.html")
    
@app.route("/", methods=["GET", "POST"])
def login():
	session.clear()
	if request.method=="POST":
		username = request.form.get("username")
		password = request.form.get("password")
		
		rows = db.execute("SELECT * FROM users WHERE username = :username", {"username": username})
		result = rows.fetchone()
		
		# Ensure username exists and password is correct
		if result == None or not check_password_hash(result[3], password):
			return render_template("error.html", message="Invalid username and/or password")
		# Remember which user has logged in
		session["username"] = result[2]
		return redirect("/home")
	return render_template("login.html")

@app.route("/forgot", methods=["GET", "POST"])
def forgot():
	session.clear()
	if request.method=="POST":
		question = request.form.get("question")
		answer = request.form.get("answer")
		fullname = request.form.get("fullname")
		username = request.form.get("username")
		password = request.form.get("password")

		#check if the details match
		rows = db.execute("SELECT * FROM users WHERE username = :username AND fullname = :fullname AND question = :question AND answer = :answer", {"username": username, "fullname": fullname, "question": question, "answer": answer}).fetchone()
		if rows is not None:
			#hash password
			pw_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
			db.execute("UPDATE users set password = :password WHERE username = :username", {"password": pw_hash, "username": username})
			db.commit()
			return render_template("login.html", msg="Password Changed!")
		else:
			return render_template("error.html", message="Details do not match")
	return render_template("forgot.html")

@app.route("/logout")
def logout():
	session.clear()
	return redirect("/")

@app.route("/home", methods=["GET", "POST"], endpoint='index')
@login_required
def index():
	username = session['username']
	if request.method=="POST":
		#keyword to be searched
		search = request.form.get("search")
		#field to be searched in
		srchparam = request.form.get("srchparam")
		if(srchparam == "title"):
			#capitalize the first letter
			search = search.capitalize()
			rows = db.execute("SELECT * FROM books WHERE title LIKE :search ",{"search": '%'+search+'%'}).fetchall()
		elif(srchparam == "author"):
			search = search.capitalize()
			rows = db.execute("SELECT * FROM books WHERE author LIKE :search ",{"search": '%'+search+'%'}).fetchall()
		elif(srchparam == "isbn"):
			rows = db.execute("SELECT * FROM books WHERE isbn LIKE :search ",{"search": '%'+search+'%'}).fetchall()
		elif(srchparam == "year"):
			rows = db.execute("SELECT * FROM books WHERE year = :search ",{"search": search}).fetchall()
		
		return render_template("index.html", rows = rows)

	#display some random books on the home page
	book_detail = db.execute("SELECT title, author FROM books ORDER BY RANDOM() LIMIT 5")
	fullname = db.execute("SELECT fullname FROM users WHERE username = :username", {"username": username}).fetchone()
	return render_template("index.html", book_detail=book_detail, fullname=fullname)

@app.route("/bookpage/<int:bookid>",methods=["GET", "POST"], endpoint='bookpage')
@login_required
def bookpage(bookid):
	msg = "notadded"
	flag = 0
	username = session["username"]
	if request.method == "POST":
		msg = "added"
		review= request.form.get("bookreview")
		rating = request.form.get("rating")
		db.execute("INSERT INTO reviews (bookid, review, username, rating) VALUES(:bookid, :review, :username, :rating)",{"bookid": bookid, "review": review, "username": username, "rating": rating})
		db.commit()
	
	result = db.execute("SELECT * FROM books WHERE id =:id ",{"id": bookid}).fetchone()
	isbns = result[0]
	reviews= db.execute("SELECT reviews.review, users.fullname, reviews.rating FROM reviews INNER JOIN users ON reviews.username = users.username WHERE reviews.bookid = :bookid  ",{"bookid": bookid}).fetchall()
	validusr= db.execute("SELECT review FROM reviews WHERE username = :username AND bookid = :bookid", {"username": username, "bookid": bookid}).fetchone()
	res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "JWezcVYXmFYbOk4TPIpOw", "isbns": isbns})
	res = res.json()
	#print(res)
	res = res['books'][0]
	#check if the user can post review or not
	if validusr is not None:
		flag=1
	return render_template("bookpage.html", result=result, reviews=reviews, msg=msg, flag=flag, res=res)

@app.route("/api/<isbn>", endpoint="apiaccess")
@login_required
def apiaccess(isbn):
	row = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
	if row is None:
		return jsonify({"error": "Invalid ISBN"})
	isbns=isbn
	res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "JWezcVYXmFYbOk4TPIpOw", "isbns": isbns})
	res = res.json()
	res = res['books'][0]
	return jsonify({
			"title": row.title,
			"author": row.author,
			"isbn": row.isbn,
			"year": str(row.year),
			"review_count": str(res['reviews_count']),
			"average_score": str(res['average_rating'])
		})