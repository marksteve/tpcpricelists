#!/usr/bin/env python

import sys
sys.path.extend(['reportlab.zip', 'requests.zip'])

from BeautifulSoup import BeautifulSoup
from StringIO import StringIO
from datetime import date
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util
from google.appengine.runtime import DeadlineExceededError
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.platypus.frames import Frame
from reportlab.platypus.tables import Table, TableStyle
import base64
import cgi
import math
import os
import requests
import simplejson as json
import time


ITEM_PER_PAGE = 72
TAB = '&nbsp;&nbsp;&nbsp;&nbsp;'
NONCE_CACHE = {}
PDF_CACHE = {}


def current_time():
  return int(time.time())


class MainHandler(webapp.RequestHandler):

  def get(self, username):
    username = cgi.escape(username)
    today = str(date.today())

    usernames = []
    pdfs = PDF_CACHE.get(today)
    if pdfs:
      usernames = str(json.dumps(pdfs.keys()))

    # Clean up cache
    for key in NONCE_CACHE.keys():
      if key + 30 * 60 < current_time():
        del NONCE_CACHE[key]

    # Generate nonce
    nonce = base64.urlsafe_b64encode(os.urandom(8))
    NONCE_CACHE[current_time()] = nonce

    # Render page
    template_file = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(template_file, {
      'usernames': usernames,
      'username': username,
      'nonce': nonce,
    }))

  def post(self, *unused):
    try:
      nonce = self.request.get('nonce')
      username = self.request.get('username')

      if nonce not in NONCE_CACHE.values():
        self.redirect('/' + username)
        return

      today = str(date.today())

      # Clean up cache
      for key in PDF_CACHE.keys():
        if key != today:
          del PDF_CACHE[key]

      base64.urlsafe_b64encode(os.urandom(30))

      # Check if cached copy is available
      pdf = None
      pdfs = PDF_CACHE.get(today)
      if pdfs:
        pdf = pdfs.get(username)

      if not pdf:

        pdf = StringIO()

        # Parse html
        try:
          soup = BeautifulSoup(
            requests.get('http://www.tipidpc.com/useritems.php?username=' + username).content
          )
        except:
          self.response.set_status(500)
          self.response.out.write("Can't connect to TPC at the moment. Please try again later.")
          return
        try:
          location, contact_no = soup.find('p', 'usermeta').findAll('em', 'red')
          location = location.string
          contact_no = contact_no.string
          item_list = []
          for tr in soup.find('table', 'itemlist').findAll('tr'):
            item, price = tr.findAll('td')
            item_list.append([item.text, price.string])
        except (AttributeError, ValueError):
          self.response.set_status(400)
          self.response.out.write('Invalid username, incomplete info (missing location/contact no) or no user items.')
          return

        # Prepare pdf values
        item_count = len(item_list)
        page_count = int(math.ceil(float(item_count) / ITEM_PER_PAGE))
        h_style = TableStyle([('FONT', (0, 0), (0, 0), 'Helvetica', 10),
                              ('FONT', (1, 0), (-1, 0), 'Helvetica', 6),
                              ('ALIGN', (1, 0), (-1, 0), 'RIGHT'),
                              ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                              ('TOPPADDING', (0, 0), (-1, -1), 0),
                              ])
        f_style = ParagraphStyle('f_style', fontName='Helvetica', fontSize=6,
                                 spaceBefore=2, leading=8, alignment=TA_CENTER)
        table_style = TableStyle([('FONT', (0, 0), (-1, -1), 'Helvetica', 8),
                                  ('TOPPADDING', (0, 0), (-1, -1), 0),
                                  ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                                  ('ROWBACKGROUNDS', (0, 0), (-1, -1), [None, HexColor(0xCCCCCC)]),
                                  ])

        # Render pdf
        c = canvas.Canvas(pdf, pagesize=LETTER)
        c.setAuthor(username)
        h = Table([[username + ' Pricelist (' + today + ')',
                    'Location: ' + location + '\n' +
                    'Contact Number: ' + contact_no,
                    ]],
                  colWidths=(4*inch, 4*inch), style=h_style)
        h.hAlign = 'LEFT'
        for i in range(0, page_count):
          t = Table(item_list[i*ITEM_PER_PAGE:(i+1)*ITEM_PER_PAGE],
                    colWidths=(6*inch, 2*inch), style=table_style)
          t.hAlign = 'LEFT'
          f = Paragraph('Page ' + str(i + 1) + '/' + str(page_count) + '<br/><br/>' +
                        'Generated by TipidPC Pricelists (tpcpricelists.appspot.com)<br/>' +
                        '<b>DISCLAIMER:</b> ' +
                        'Availability and prices are subject to change without prior notice.',
                        f_style)
          Frame(0.25*inch, 0.25*inch, 8*inch, 10.5*inch).addFromList([h, t, f], c)
          c.showPage()
        c.save()

        # Store in cache
        if not pdfs:
          PDF_CACHE[today] = {}
        PDF_CACHE[today][username] = pdf

      # Set Headers
      self.response.headers['Content-Type'] = 'application/pdf'
      self.response.headers['Content-Disposition'] = (
        'attachment; filename=' + username + '_pricelist_' + today.replace('-', '_') + '.pdf'
      )
      # Write pdf to response
      self.response.out.write(pdf.getvalue())

    except DeadlineExceededError:
      self.response.set_status(500)
      self.response.out.write('Timeout.')


def main():
  application = webapp.WSGIApplication([
    (r'/(.*)', MainHandler),
  ], debug=False)
  util.run_wsgi_app(application)


if __name__ == '__main__':
  main()
