# -*- coding: utf-8 -*-
# Part of Dynexcel.
{
    "name": "POS FBR Connector",
    
    "author": "Dynexcel",
    
    "website": "https://www.dynexcel.com",

    "support": "info@dynexcel.com",
        
    "version": "11.0.3",
    
    "category": "Point Of Sale",
    
    "summary": "POS FBR Connector",
        
    "description": """  
POS FBR Connector

 """,
     
    "depends": ['point_of_sale','base','web','de_pos_receipt', 'account'],
    
    "data": [
        "views/views.xml",
        "data/data.xml",
        "views/templates.xml"
    ],    
    "qweb":["static/src/xml/*.xml"],
    "images": [],
    "installable": True,
    "auto_install": False,
    "application": True,        
}