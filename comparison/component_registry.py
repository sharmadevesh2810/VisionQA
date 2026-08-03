"""
==============================================================================
VisionQA - Component Registry
==============================================================================

Copyright (c) 2026 Devesh Sharma.
All Rights Reserved.

Author      : Devesh Sharma
Framework   : VisionQA

Defines the UI components VisionQA can detect.
"""

COMPONENT_RULES = {

    "header": [
        ".ant-layout-header",
        "header",
    ],

    "sidebar": [
        ".ant-layout-sider",
        "aside",
        "nav",
    ],

    "breadcrumb": [
        ".ant-breadcrumb",
    ],

   "search": [
    ".ant-input-search input",
    "input[placeholder*='Search']",
    "input[type='search']",
],

    "filter": [
        ".ant-select",
    ],

    "table": [
    ".ant-table",
    ".ant-table-wrapper",
    "table",
],

    "pagination": [
        ".ant-pagination",
    ],

    "button": [
        "button",
        ".ant-btn",
    ],

    "form": [
        "form",
    ],

    "modal": [
        ".ant-modal",
    ],

    "tabs": [
        ".ant-tabs",
    ],

}