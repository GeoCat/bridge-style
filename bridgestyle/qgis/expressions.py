from qgis.core import QgsExpressionNode, QgsExpression

class UnsupportedExpressionException(Exception):
    pass

binaryOps = [
     "Or",
    "And",
     "PropertyIsEqualTo",
     "PropertyIsNotEqualTo",
     "PropertyIsLessThanOrEqualTo",
     "PropertyIsGreaterThanOrEqualTo",
     "PropertyIsLessThan",
     "PropertyIsGreaterThan",
     None, None, None, None, None, None, None,
     "Add",
      "Sub",
      "Mul",
      "Div",
      None, None, None, None]

unaryOps = ["Not", None]

functions = {"radians": "toRadians",
             "degrees": "toDegrees",
             "floor": "floor",
             "ceil": "ceil",
             "area": "area",
             "buffer": "buffer",
             "centroid": "centroid",
             "if": "if_then_else",
             "bounds": "envelope",
             "distance": "distance",
             "convex_hull": "convexHull",
             "end_point": "endPoint",
             "start_point": "startPoint",
             "x": "getX",
             "y": "getY",
             "concat": "Concatenate",
             "substr": "strSubstr",
             "lower": "strToLower",
             "upper": "strToUpper",
             "replace": "strReplace",
             "exterior_ring": "exteriorRing",
             "intersects": "intersects",
             "overlaps": "overlaps",
             "touches": "touches",
             "within": "within",
             "relates":"relates",
             "crosses": "crosses",
             "disjoint": "disjoint",
             "geom_from_wkt": "geomFromWKT",
             "perimeter": "geomLength",
             "union": "union",
             "acos":"acos",
             "asin": "asin",
             "atan": "atan",
             "atan2": "atan2",
             "sin": "sin",
             "cos": "cos",
             "tan": "tan",
             "ln": "log",
             "title": "strCapitalize",
             "translate": "offset",
             "min": "min",
             "max": "max"
             } #TODO

def walkExpression(node):
    if node.nodeType() == QgsExpressionNode.ntBinaryOperator:
        exp = handleBinary(node)
    elif node.nodeType() == QgsExpressionNode.ntUnaryOperator:
        exp = handleUnary(node)
    #elif node.nodeType() == QgsExpressionNode.ntInOperator:
        #filt = handle_in(node)
    elif node.nodeType() == QgsExpressionNode.ntFunction:
        exp = handleFunction(node)
    elif node.nodeType() == QgsExpressionNode.ntLiteral:
        exp = handleLiteral(node)
    elif node.nodeType() == QgsExpressionNode.ntColumnRef:
        exp = handleColumnRef(node)
    #elif node.nodeType() == QgsExpression.ntCondition:
    #    filt = handle_condition(nod)
    return exp

def handleBinary(node):
    op = node.op()
    retOp = binaryOps[op]
    left = node.opLeft()
    right = node.opRight()
    retLeft = walkExpression(left)
    retRight = walkExpression(right)
    return [retOp, retLeft, retRight]

def handleUnary(node):
    op = node.op()
    operand = node.operand()
    retOp = unaryOps[op]
    retOperand = walkExpression(operand)
    return [retOp, retOperand]

def handleLiteral(node):
    val = node.value()
    quote = ""
    if isinstance(val, basestring):
        quote = "'"
        val = val.replace("\n", "\\n")
    elif val is None:
        val = "null"
    return val

def handleColumnRef(node):
    return ["PropertyName", node.name()]

def handleFunction(node):
    fnIndex = node.fnIndex()
    func = QgsExpression.Functions()[fnIndex].name()
    if func == "$geometry":
        return ["PropertyName", "the_geom"]
    elif func in functions:        
        elems = [functions[func]]
        args = node.args()
        if args is not None:
            args = args.list()
            for arg in args:
                elems.append(walkExpression(arg))
        return elems
    else:
        raise UnsupportedExpressionException("Unsupported function in expression: '%s'" % func)    
