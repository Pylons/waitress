import sys

if __name__ == '__main__':
    try:
        from urllib.request import Request, urlopen
    except ImportError:
        from urllib2 import Request, urlopen

    url = sys.argv[1]
    headers = {'Content-Type':'text/plain; charset=utf-8'}
    resp = urlopen(url)
    line = resp.readline().decode('ascii') # py3
    sys.stdout.write(line)
    sys.stdout.flush()
    
