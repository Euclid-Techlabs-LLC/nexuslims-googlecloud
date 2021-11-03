import os
from typing import Dict
import traceback
import logging

import pymysql
from flask import Flask, jsonify, request
from flask.typing import ResponseReturnValue
from werkzeug.exceptions import BadRequest

from database import Database

db_user = os.getenv('CLOUD_SQL_USERNAME')
db_password = os.getenv('CLOUD_SQL_PASSWORD')
db_name = os.getenv('CLOUD_SQL_DATABASE_NAME')
db_connection_name = os.getenv('CLOUD_SQL_CONNECTION_NAME')

app_username = os.getenv("NEXUSLIMS_DBAPI_USERNAME")
app_password = os.getenv("NEXUSLIMS_DBAPI_PASSWORD")

app = Flask(__name__)
logger = logging.getLogger(__name__)


def _get_db_conn_kwargs() -> Dict:
    res = {}
    # When deployed to App Engine, the `GAE_ENV` environment variable will be
    # set to `standard`
    if os.getenv('GAE_ENV') == 'standard':
        # If deployed, use the local socket interface for accessing Cloud SQL
        res["unix_socket"] = '/cloudsql/{}'.format(db_connection_name)
    else:
        # If running locally, use the TCP connections instead
        # Set up Cloud SQL Proxy (cloud.google.com/sql/docs/mysql/sql-proxy)
        # so that your application can use 127.0.0.1:3306 to connect to your
        # Cloud SQL instance
        res["host"] = "127.0.0.1"

    return res


@app.route("/api/instrument", methods=["GET"])
def instrument() -> ResponseReturnValue:
    auth = request.authorization
    if not auth \
            or auth.username != app_username \
            or auth.password != app_password:
        return jsonify(isError=True,
                       message="Unauthorized",
                       statusCode=401), 401

    cid = request.args.get("computer_name", type=str)

    kwargs = _get_db_conn_kwargs()
    kwargs["cursorclass"] = pymysql.cursors.DictCursor
    try:
        with Database(db_user, db_password, db_name, **kwargs) as db:
            sql = "SELECT * FROM instruments WHERE computer_name=%s;"
            db.execute(sql, (cid,))
            res = db.fetchone()
    except Exception:
        logger.exception(f"Database error for request {request.url}")
        return jsonify(isError=True,
                       message="Database error, query failure",
                       detail=traceback.format_exc(),
                       url=request.url,
                       statusCode=500), 500
    if not res:
        return jsonify(isError=True,
                       message="Entry not found",
                       url=request.url,
                       statusCode=404), 404

    return jsonify(isError=False,
                   message="Success",
                   statusCode=200,
                   data=res), 200


@app.route("/api/instrumentlist", methods=["GET"])
def instruments() -> ResponseReturnValue:
    auth = request.authorization
    if not auth \
            or auth.username != app_username \
            or auth.password != app_password:
        return jsonify(isError=True,
                       message="Unauthorized",
                       statusCode=401), 401

    kwargs = _get_db_conn_kwargs()
    kwargs["cursorclass"] = pymysql.cursors.DictCursor
    try:
        with Database(db_user, db_password, db_name, **kwargs) as db:
            sql = "SELECT * FROM instruments"
            res = db.query(sql)
    except Exception:
        logger.exception(f"Database error for request {request.url}")
        return jsonify(isError=True,
                       message="Database error, query failure",
                       detail=traceback.format_exc(),
                       url=request.url,
                       statusCode=500), 500

    return jsonify(isError=False,
                   message="Success",
                   statusCode=200,
                   data=res), 200


@app.route("/api/lastsession", methods=["GET"])
def last_session() -> ResponseReturnValue:
    auth = request.authorization
    if not auth \
            or auth.username != app_username \
            or auth.password != app_password:
        return jsonify(isError=True,
                       message="Unauthorized",
                       statusCode=401), 401

    cid = request.args.get("instrument", default=None)
    sid = request.args.get("session_identifier", default=None)
    event = request.args.get("event_type", default="START")

    kwargs = _get_db_conn_kwargs()
    kwargs["cursorclass"] = pymysql.cursors.DictCursor
    try:
        with Database(db_user, db_password, db_name, **kwargs) as db:
            if cid is not None:  # query last session log on this instrument
                sql = ("SELECT * FROM session_log WHERE instrument=%s "
                       "AND event_type!='RECORD_GENERATION'"
                       "ORDER BY timestamp DESC LIMIT 1;")
                db.execute(sql, (cid,))
            else:  # verify last session log insertion
                sql = ("SELECT * FROM session_log WHERE session_identifier=%s "
                       "AND event_type=%s ORDER BY timestamp DESC LIMIT 1;")
                db.execute(sql, (sid, event))
            res = db.fetchone()
    except Exception:
        logger.exception(f"Database error for request {request.url}")
        return jsonify(isError=True,
                       message="Database error, query failure",
                       detail=traceback.format_exc(),
                       url=request.url,
                       statusCode=500), 500
    if not res:
        return jsonify(isError=True,
                       message="Entry not found",
                       url=request.url,
                       statusCode=404), 404

    return jsonify(isError=False,
                   message="Success",
                   statusCode=200,
                   data=res), 200


@app.route("/api/session", methods=["GET", "POST", "PUT"])
def session() -> ResponseReturnValue:
    auth = request.authorization
    if not auth \
            or auth.username != app_username \
            or auth.password != app_password:
        return jsonify(isError=True,
                       message="Unauthorized",
                       statusCode=401), 401

    kwargs = _get_db_conn_kwargs()

    if request.method == 'GET':
        sid = request.args.get("id_session_log")
        kwargs["cursorclass"] = pymysql.cursors.DictCursor
        try:
            with Database(db_user, db_password, db_name, **kwargs) as db:
                sql = "SELECT * FROM session_log WHERE id_session_log=%s;"
                db.execute(sql, (sid,))
                res = db.fetchone()
        except Exception:
            logger.exception(f"Database error for request {request.url}")
            return jsonify(isError=True,
                           message="Database error, query failure",
                           detail=traceback.format_exc(),
                           url=request.url,
                           statusCode=500), 500
        if not res:
            return jsonify(isError=True,
                           message="Entry not found",
                           url=request.url,
                           statusCode=404), 404

        return jsonify(isError=False,
                       message="Success",
                       statusCode=200,
                       data=res), 200

    if request.method == "PUT":
        sid = request.form.get("id_session_log", default=None)
        # uuid = request.form.get("session_identifier", default=None)
        status = request.form.get("record_status", default="TO_BE_BUILT")
        note = request.form.get("session_note", default="")
        try:
            with Database(db_user, db_password, db_name, **kwargs) as db:
                if not sid:
                    msg = "Invalid request: `id_session_log` must to be set."  # noqa
                    raise BadRequest(msg)
                if status:
                    sql = "UPDATE session_log SET record_status=%s WHERE id_session_log=%s"  # noqa
                    db.execute(sql, (status, sid,))
                if note:
                    sql = "UPDATE session_log SET session_note=%s WHERE id_session_log=%s"  # noqa
                    db.execute(sql, (note, sid,))
        except BadRequest:
            return jsonify(isError=True,
                           message="BadRequest error",
                           detail=traceback.format_exc(),
                           url=request.url,
                           statusCode=400), 400
        except Exception:
            logger.exception(f"Database error for request {request.url}")
            return jsonify(isError=True,
                           message="Database error, update failure",
                           detail=traceback.format_exc(),
                           url=request.url,
                           statusCode=500), 500

        return jsonify(isError=False,
                       message="Success",
                       statusCode=200), 200

    if request.method == "POST":
        cid = request.form.get("instrument")
        event = request.form.get("event_type")
        status = request.form.get("record_status", default="WAITING_FOR_END")
        user = request.form.get("user", default=None)
        uuid = request.form.get("session_identifier")
        note = request.form.get("session_note", default="")

        if not cid or not event or not uuid:
            msg = "BadRequest: `instrument` & `event_type` & `session_identifier` params must be set."  # noqa
            return jsonify(isError=True,
                           message="BadRequest error",
                           detail=msg,
                           url=request.url,
                           statusCode=400), 400

        try:
            with Database(db_user, db_password, db_name, **kwargs) as db:
                sql = ("INSERT INTO session_log "
                       "(instrument,event_type,record_status,user,session_identifier,session_note) "  # noqa
                       "VALUES(%s,%s,%s,%s,%s,%s);")
                db.execute(sql, (cid, event, status, user, uuid, note))
        except Exception:
            logger.exception(f"Database error for request {request.url}")
            return jsonify(isError=True,
                           message="Database error, insertion failure",
                           detail=traceback.format_exc(),
                           url=request.url,
                           statusCode=500), 500

        return jsonify(isError=False,
                       message="Success",
                       statusCode=200), 200


@app.route("/api/sessionlist", methods=["GET"])
def sessions() -> ResponseReturnValue:
    auth = request.authorization
    if not auth \
            or auth.username != app_username \
            or auth.password != app_password:
        return jsonify(isError=True,
                       message="Unauthorized",
                       statusCode=401), 401

    status = request.args.get("record_status", type=str)

    kwargs = _get_db_conn_kwargs()
    kwargs["cursorclass"] = pymysql.cursors.DictCursor
    try:
        with Database(db_user, db_password, db_name, **kwargs) as db:
            sql = "SELECT * FROM session_log WHERE record_status=%s"
            res = db.query(sql, (status,))
    except Exception:
        logger.exception(f"Database error for request {request.url}")
        return jsonify(isError=True,
                       message="Database error, query failure",
                       detail=traceback.format_exc(),
                       url=request.url,
                       statusCode=500), 500

    return jsonify(isError=False,
                   message="Success",
                   statusCode=200,
                   data=res), 200


@app.route("/api/buildrecords", methods=["GET"])
def buildrecords() -> ResponseReturnValue:
    # only requst from AppEngine Cron service is allowed
    if not request.headers.get("X-Appengine-Cron"):
        return jsonify(isError=True,
                       message="Unauthorized",
                       statusCode=401), 401

    try:
        from nexuslims.record import build
        res = build(verbose=logging.DEBUG)
        return jsonify(isError=False,
                       message="Success",
                       data=res,
                       statusCode=200), 200
    except Exception:
        logger.exception("Record building failure")
        return jsonify(isError=True,
                       message="Record building failure",
                       detail=traceback.format_exc(),
                       url=request.url,
                       statusCode=500), 500


@app.route('/')
def main():
    return "API for nexuslims-db"


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
