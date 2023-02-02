from flask import Flask, redirect, render_template, request
import anirequests as an


app = Flask(__name__)

@app.route("/compare")
def compare():
    user_1 = request.args.get("u1")
    user_2 = request.args.get("u2")
    content1, code_1 = an.retrieve_data(user_1)
    content2, code_2 = an.retrieve_data(user_2)
    if code_1 == 200 & code_2 == 200:
        df1,u1 = an.get_data_from_json(content1)
        df2,u2 = an.get_data_from_json(content2)
        data = an.get_data(df1,df2,u1,u2)
        return render_template("compare.html",data=data)
    else:
        return render_template("compare_error.html",data={'code_1':code_1,'code_2':code_2})

@app.route("/")
def index():
    return render_template("index.html")

