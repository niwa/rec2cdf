# Aims

1. By inspecting a spatial file, it should be
   possible to determine the version of
   the rec2cdf code, and which version of the
   geofabric database was used in its generation;
   and to regenerate the file using those specific
   versions.

2. What changes to the code or geofabric were done
   to produce a particular version of the code or
   geofabric.

3. The ability for a user to easily report code or
   database issues they are having, and the
   resolution of that to be tracked all they way
   through to spatial file generation.

# Versioning

The rec2cdf code sets the spatial file meta-data attribute `code_version` to
that found in `bin/version.txt`.  The format of the version string in
`bin/version.txt` doesn't really matter, it is just a string that will be
embedded in spatial files and used to tag code releases.  However the current
format is:
```
<major>.<minor>.<revision>
```
and the `<revision>` is incremented by CI/CD when pushing the repository (see
section [CI/CD](#CI/CD) below).

The database version is also set in the spatial file meta-data under the
attributes `source` and `db_version`.  Source is the database name and server,
and the `db_version` comes from the version column in the changelog table in
the database that rec2cdf is using.  Using `source` and `db_version` one can
access the snapshotted version of the database (probably on
`wellhydrodbdev.niwa.local`).

## CI/CD

When rec2cdf code is pushed, a pipeline runs which updates the version or tags
the code.  What is done depends on which branch is receiving the push:

* Non-main branch.  The gitlab variable LASTVERSION which has the
  format
  ```
  <major>.<minor>.<revision>
  ```
  has the third part (the `revision`) incremented by one, and this string put
  into `bin/version.txt`, and another commit/push performed.  This means
  developers do not need to manage the versioning themselves (except remember
  to pull after a push since every manual push results in that second automatic
  push).  When rec2cdf runs it puts the version string found in
  `bin/version.txt` into the spatial file.  Major or minor version numbers are
  manually updated in the Variables section in
  [gitlab](https://git.niwa.local/hydro-proc/rec2cdf/-/settings/ci_cd).  The
  fact a gitlab variable is used means that version numbers are unique even
  across branches.
* Main branch.  The main branch is protected: developers can't push
  directly into the main branch.  When a merge of another branch into the main
  branch is performed the version found in `bin/version.txt` is used to
  tag the code.  Note that the LASTVERSION variable is not used since that
  might have run ahead due to development in other branches.

  Users should only use a tagged rec2cdf release (in other words the main
  branch).  Since this tag is the version in `bin/version.txt` and thus the
  spatial file, the user can easily find the code that produced the spatial
  file.  If a non-main branch version of rec2cdf is used the version found in
  the spatial file will fall between two tagged versions, making it more
  difficult for the user to figure out exactly what code was used.  It would be
  easy for CI/CD to tag every single push, but then we would have many many tags, most
  likely causing more confusion (and also encouraging people to use code
  from any branch, thus encouraging non-main branch longevity!).


# Updating code and/or database

This is also documented on the [wiki](https://oneniwa.atlassian.net/wiki/spaces/HAFS/pages/59933979/GeoFrabric+databases)
and [JIRA ticket](https://oneniwa.atlassian.net/wiki/spaces/HAFS/pages/59933839/Version+control+of+Hydrological+model+ancillary+data+and+station+data)

When a change to the code and/or database *maybe*
required an issue should be created on the [issue](https://git.niwa.local/hydro-proc/rec2cdf)
page.
Even if someone wants to discuss a *potential* problem, they should put it
in an issue.  Because email is not tracked or centrally archived it is not a good way of
discussing problems with the code.  It is too easy for a huge long email
discussion to result in a change that our future selves won't remember or
understand since the discussion hasn't been kept in one archived location.

The issue should be appropriately tagged (DB,
REC1, REC2, DN3, suggestion, bug...).  In the
future JIRA maybe linked to gitlab issues, but
this will be after JIRA has been migrated to the
cloud and feasibility/cost/benefit study done.

Often it isn't clear what the required change is, and the issue may get long
and convoluted.  Because someone in the future may want to read why a change
was done, whoever is in charge of making code/db changes should summarize the
issue and proposed changes.

* Code.  If a change to the rec2cdf code is needed then:

    1. A branch should be made (this can be done by hitting the Create branch
       drop down button within the issue on gitlab).  The branch's name will start
       with the issue number.  As an example suppose the issue was 'Zero slopes'
       and was issue number 7, then the branch will be '7-zero-slopes'.
    2. Code developed in the new branch, any commit messages should reference the
       issue number by putting a #x in the commit message where x is the issue
       number, eg 'Enlarge the slope datatype, ref #7'.  Frequently committing and
       pushing into the development branch is encouraged, especially if there are a
       lot of changes required, this allows others to see and test development.
       Every push results in `bin/version.txt` being updated, so you should always
       pull after doing a push.
    3. When you are happy  with your changes, hit the 'Create merge request' button in the
       issue in gitlab.
    4. The branch can now be merged back into main; a tag will automatically be
       generated when successfully merged.

    Branches are for testing and developing new things, not to fork off
    indefinitely.

* Database.  If a change to the database is needed, the required changes should
  be done on the development database on `wellhydrodbdev.niwa.local`, the
  changelog in the database updated, and the database snapshotted and pushed to
  production as described by
  [db versioning](https://git.niwa.local/hydro-proc/versioning_rec_databases.git).

## Git GUI instructions

Here follows detailed instructions on how to deal with a code change

1. After the branch has been made on git.niwa.local in Git GUI go to Remote ->
   Fetch from -> origin.  You should see a window popup with the new branch
   being fetched.
2. Make a new local branch to track the new one by going to Branch -> Create,
   then click on `Match Tracking Branch Name` and
   selecting the branch. Click `Create`.  Ensure that at the bottom of the Git
   GUI window you see `Checked out <branch name>`
3. Do whatever development you need to do.
4. Do a commit/push in the usual manner (click `Recan`, click `Stage Changed`,
   write a message, click `Commit`, and click `Push`).
5. Your changes are up on git.niwa.local.  What you now do depends on whether
   you anticipate doing any more development.  If you do, then first you should
   Remote -> Fetch from -> origin, Merge -> Local merge, then select the
   Tracking branch, so you get the latest `bin/version.txt` which has been
   bumped up by CI/CD.  Then repeat step 4 and 5 until finished development.
6. On git.niwa.local create the merge request and get that processed as discussed above.
7. Checkout the main branch by going to Branch -> Checkout, picking main and clicking Checkout.
8. Delete the local development branch by going to Branch -> Delete and
   selecting the local branch.

# TODO

Once the CI/CD is in place on git.niwa.local we can incorporate some tests that
are automatically run on pushing code.

