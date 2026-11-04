"""Small synthetic Gmail response builders shared by protocol/sync tests."""


def pdf(name='statement.pdf', **body):
    return dict(filename=name, mimeType='application/pdf', body={'size':8, **body})
