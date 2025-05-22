# Hack to add cdata with xml.etree
from xml.etree import ElementTree

ElementTree._original_serialize_xml = ElementTree._serialize_xml


def _serialize_xml(write, elem, qnames, namespaces,short_empty_elements, **kwargs):
    if elem.tag == '![CDATA[':
        write("<{}{}]]>".format(elem.tag, elem.text))
        if elem.tail:
            write(ElementTree._escape_cdata(elem.tail))
    else:
        return ElementTree._original_serialize_xml(write, elem, qnames, namespaces,short_empty_elements, **kwargs)


ElementTree._serialize_xml = ElementTree._serialize['xml'] = _serialize_xml