#!/usr/bin/env python3

"""RECTableCheck

Tests REC database tables for missing data.

Block of comments
"""

import psycopg2
import logging

# set global variables for database access
# these will be parameters when the program is
# worked out a bit more
dbhost = "localhost"
dbname = "rec2"
dbuser = "spatialuser"
# dbpass = "once43king"
dbpass = "Jaih7ohbvufogu6O"

# logging configuration
logfile = "dbTestPy.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%a, %d %b %Y %H:%M:%S",
    filename=logfile,
    filemode="a",
)


def isPostgresNumType(tName):
    """Return True if tName names a numerical type for PostgreSQL. Otherwise return False"""
    if not isinstance(tName, str):
        return False
    if tName.upper().split()[0] in (
        "REAL",
        "DOUBLE",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "NUMERIC",
    ):
        return True
    else:
        return False


def isPostgresCharType(tName):
    """Return True if tName names a character type for PostgreSQL. Otherwise return False"""
    if not isinstance(tName, str):
        return False
    if tName.upper().split()[0] in ("CHARACTER", "TEXT", "VARCHAR", "STRING"):
        return True
    else:
        return False


def getDBTableNames(db):
    """Retrieve all the table names from database db."""
    queryTxt = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"

    # Submit Query to REC database
    logging.debug("getDBTableNames: Executing REC SQL data query")
    try:
        dbcur = db.cursor()
        dbcur.execute(queryTxt)
    except Exception as e:
        try:
            dbcur.close()
        except:
            pass
        logging.error("getDBTableNames: Could not execute REC SQL")
        logging.error("Message: " + str(e))
        raise

    # Handle empty Return
    if dbcur.rowcount == 0:
        dbcur.close()
        logging.warning("getDBTableNames: No Data returned from REC Return")
        return []
    value = []
    for row in dbcur.fetchall():
        value.append(row[0])
    dbcur.close()
    return value


def getTableFieldNames(db, tableName, nameIndex=3):
    """Return a list of all the field (column) names in the given table in the given database."""
    queryTxt = (
        "SELECT * FROM information_schema.columns "
        "WHERE table_schema = 'public' AND "
        " table_name = {};"
    ).format(tableName)
    # Query REC database
    logging.debug("getTableFieldNames: Executing REC SQL data query")
    logging.debug("Query: \n" + queryTxt)
    try:
        dbcur = db.cursor()
        dbcur.execute(queryTxt)
    except Exception as e:
        try:
            dbcur.close()
        except:
            pass
        logging.error("getTableFieldNames: Could not execute REC SQL")
        logging.error("Message: " + str(e))
        return []
    value = []
    for row in dbcur.fetchall():
        value.append(row[nameIndex])
    return value


def getTableFieldNamesTypes(db, tableName, nameIndex=3, typeIndex=7, nullableIndex=6):
    """Return a list of tuples containing all the field (column) names in the named table in database db,
    along with their data types and whether they're nullable
    (
        Field Name -- e.g. rchid, cen_lon
        Field Type -- e.g. bigint, double precision
        NULLABLE -- YES or NO
    )"""
    queryTxt = "SELECT * FROM information_schema.columns \n"
    queryTxt += "WHERE table_schema = 'public' AND table_name = %s;"
    # Query REC database
    logging.debug("getTableFieldNames: Executing REC SQL data query")
    logging.debug("Query: \n" + queryTxt % tableName)
    try:
        dbcur = db.cursor()
        dbcur.execute(queryTxt, (tableName,))
    except Exception as e:
        try:
            dbcur.close()
        except:
            pass
        logging.error("getTableFieldNames: Could not execute REC SQL")
        logging.error("Message: " + str(e))
        return []
    value = []
    for row in dbcur.fetchall():
        value.append((row[nameIndex], row[typeIndex], row[nullableIndex]))
    return value


def nullCountsByField(db, tableName):
    """Return a dictionary containing, for each field in the data table,
    the count of null entries for the given field. The first entry in
    the dictionary has key of "TOTAL_ROW_COUNT" and value equal to the
    total number of rows in the table.
    """
    queryTxt = "SELECT COUNT(*) FROM {};".format(tableName)
    logging.debug("nullCountsByField: Executing REC SQL data query")
    logging.debug("Query: \n" + queryTxt)

    try:
        dbcur = db.cursor()
        dbcur.execute(queryTxt)
    except Exception as e:
        try:
            dbcur.close()
        except:
            pass
        logging.error("nullCountsByField: Could not execute REC SQL")
        logging.error("Message: " + str(e))
        return {}
    value = {"TOTAL_ROW_COUNT": dbcur.fetchone()[0]}

    for field in getTableFieldNamesTypes(db, tableName):
        nullCnt = 0
        if field[2].upper() == "YES":
            queryTxt = "SELECT COUNT(*) FROM {}\n".format(tableName)
            queryTxt += "WHERE {} = NULL;".format(field[0])
            dbcur.execute(queryTxt)
            nullCnt = dbcur.fetchone()[0]
        queryTxt = "SELECT COUNT(*) FROM {}\n".format(tableName)
        queryZeroes = False
        if isPostgresNumType(field[1]):
            queryTxt += "WHERE {} = 0;".format(field[0])
            queryZeroes = True
        if isPostgresCharType(field[1]):
            queryTxt += "WHERE ({} <> '') IS NOT TRUE;".format(field[0])
            queryZeroes = True
        if queryZeroes:
            dbcur.execute(queryTxt)
            zbCnt = dbcur.fetchone()[0]
        else:
            zbCnt = 0
        value[field[0]] = (nullCnt, zbCnt)

    return value


def findPairs(strList, a, b):
    """ "Return a list of pairs and indices from strings in the list.
    arguments ['a1', 'b1', 'a2', 'b2'], '1', '2'
    will return [('a1', 'a2', 0, 2), ('b1', 'b2', 1, 3)]
    """
    value = []
    i = 0
    for item in strList:
        try:
            if item.endswith(a):
                afront = item[0 : item.rfind(a)]
                bitem = afront + b
                j = strList.index(bitem)
                value.append((item, bitem, i, j))
        except:
            pass
        i += 1
    return value


def inNZll(lon, lat, checkSign=True):
    """Return True if lon, lat are numbers falling within a very crude
    longitude/latitude box around New Zealand. Otherwise return False.
    """
    try:
        if not checkSign:
            lon = abs(lon)
            lat = -1.0 * abs(lat)
        if lon < 166.3 or lon > 178.6 or lat > -34.4 or lat < -47.3:
            return False
        else:
            return True
    except:
        return False


def inNZxy(x, y, checkSign=True):
    """Return True if x, y are numbers falling within a very crude NZTM2000
    northing/easting box around New Zealand. Otherwise return False.
    """
    try:
        if not checkSign:
            x = abs(x)
            y = abs(y)
        if x < 1090000.0 or x > 2090000.0 or y < 4745000.0 or y > 6200000.0:
            return False
        else:
            return True
    except:
        return False


def tableLocationOutliers(db, tableName):
    """Return a list of tuples, each representing a position that
    is inconsistent with the known location of the thing represented
    in the database. Tuples are composed of
    (
        X Coordinate Field Name -- e.g. out_lon, out_x
        Y Coordinate Field Name -- e.g. out_lon, out_y
        ID field name -- e.g. reachid, lakeid
        ID field value -- e.g. 8176644
        Test(s) failed -- e.g. inNZ, inRegion
    )
    """
    # Find out if our table has any coordinate information
    fields = getTableFieldNamesTypes(db, tableName)
    coordFields = []
    idFields = []
    for field in fields:
        if field[0].upper().endswith("ID"):
            idFields.append(field[0])
        if (
            field[0].upper().endswith("_X")
            or field[0].upper().endswith("_Y")
            or field[0].upper().endswith("_LAT")
            or field[0].upper().endswith("_LON")
        ):
            # field[0].upper() == "NORTHING" or
            # field[0].upper() == "EASTING" or
            # field[0].upper() == ("LAT") or
            # field[0].upper() == ("LON")):
            coordFields.append(field[0])
    if len(idFields) == 0:
        logging.info("No IDs in table " + tableName)
        # return []
    if len(coordFields) == 0:
        logging.info("No coordinates in table " + tableName)
        return []

    # narrow potential ID fields down to just one.
    idStr = idFields[0]  # default
    if len(idFields) > 1:
        looking = True
        # if there's a plain "id" field, that's our choice
        for field in idFields:
            if field.upper() == "ID":
                idStr = field
                looking = False
        # if necessary, we'll favor "rchid" next
        if looking:
            for field in idFields:
                if field.upper() == "RCHID":
                    idStr = field
                    looking = False
        # if necessary, we'll favor "lakeid" next
        if looking:
            for field in idFields:
                if field.upper() == "LAKEID":
                    idStr = field
                    looking = False

    xyPairs = findPairs(coordFields, "_x", "_y")
    for pair in findPairs(coordFields, "easting", "northing"):
        xyPairs.append(pair)
    llPairs = findPairs(coordFields, "lon", "lat")

    dbcur = db.cursor()

    outliers = []
    for pair in xyPairs:
        # Assemble an outlier-finding query
        dbcur.execute(
            (
                "SELECT {}, {}, {}\nFROM {}\n"
                "WHERE {} < %s OR {} > %s\nOR "
                "{} < %s OR {} > %s"
            ).format(
                idStr, pair[0], pair[1], tableName, pair[0], pair[0], pair[1], pair[1]
            ),
            (1090000.0, 2090000.0, 4745000.0, 6200000.0),
        )
        for row in dbcur.fetchall():
            outliers.append(
                (idStr, row[0], pair[0], pair[1], row[1], row[2], "Outside NZ")
            )
    for pair in llPairs:
        dbcur.execute(
            (
                "SELECT {}, {}, {}\nFROM {}\n"
                "WHERE {} < %s OR {} > %s\nOR "
                "{} < %s OR {} > %s"
            ).format(
                idStr, pair[0], pair[1], tableName, pair[0], pair[0], pair[1], pair[1]
            ),
            (166.3, 178.6, -47.3, -34.4),
        )
        for row in dbcur.fetchall():
            outliers.append(
                (idStr, row[0], pair[0], pair[1], row[1], row[2], "Outside NZ")
            )

    dbcur.close()

    return outliers


def main():
    logging.info("main: Opening connection to DB " + dbname)
    try:
        db = psycopg2.connect(
            host=dbhost, user=dbuser, password=dbpass, database=dbname
        )
    except Exception as e:
        logging.error("main: Could not connect to REC DB: " + dbname)
        logging.error("Message: " + str(e))
        return -1

    for tName in getDBTableNames(db):
        print(tName)
        for t in tableLocationOutliers(db, tName):
            print(t)
        print()

    for tName in getDBTableNames(db):
        print("Table = " + tName + ":")
        nullDict = nullCountsByField(db, tName)
        print("    Table contains %d rows" % nullDict["TOTAL_ROW_COUNT"])
        for field in getTableFieldNamesTypes(db, tName):
            msg = "    " + field[0] + ": " + field[1] + ", "
            if field[2].upper() == "YES":
                msg += "%d NULLS" % nullDict[field[0]][0]
            else:
                msg += "NOT NULLABLE"
            msg += ", %d Zeroes or blanks" % nullDict[field[0]][1]
            print(msg)
    logging.info("main: Closing connection to DB " + dbname)
    db.close()
    return 0


# if (__name__ == "main"):
if True:
    main()
