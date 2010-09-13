All your pure python dependencies in one place::

    pip install -I --install-option='--home=/Users/Jeff/dev/flask/vendor' -r requirements/prod.txt

    # freddo.pth
    import site; site.addsitedir('vendor/lib/python')
