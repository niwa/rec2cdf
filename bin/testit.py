def testit(v, tol):
    print(v, end="")
    if v not in d:
        print(" MISSING from d")
        return
    if v not in dnew:
        print(" MISSING from dnew")
        return
    dnew.dsrch_rchid.values
    left = d[v]
    right = dnew[v]
    if v == "dsrch_rchid":
        left = left[1:]
        right = right[1:]
    elif v == "uprch_nrch":
        left.values.sort(axis=1)
        right.values.sort(axis=1)
    # can't do station name
    if v == "station_name":
        print()
        return
    if np.allclose(left, right, rtol=tol, equal_nan=True):
        print()
    else:
        print(" NOT CLOSE")
