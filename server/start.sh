#!/bin/bash
gunicorn -w 4 server.main:app --bind 0.0.0.0:8080
