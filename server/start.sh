#!/bin/bash
gunicorn -w 4 main:app --bind 0.0.0.0:8080
