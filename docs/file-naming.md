# File Naming
The agent will try to match your file automatically, usually based on the filename. You can assist it by renaming your video appropriately.
If the video is not successfully matched, you can try to manually match it using the [Match...] function in Plex. See the [manual searching document](./manualsearch.md) for more information.
Best practice for each site is listed in the [sitelist document](./sitelist.md).

**Either the `Plex Video Files Scanner` or the `Plex Movie Scanner` can be used as the library scanner.**

#### Here are Some Naming Structures We Recommend:
- `SiteName` - `YYYY-MM-DD` - `Scene Name` `.[ext]`
- `sitename`.`YY.MM.DD`.`scene.name` `.[ext]`
- `SiteName` - `Scene Name` `.[ext]`
- `sitename`.`scene.name` `.[ext]`
- `SiteName` - `YYYY-MM-DD` - `Actor(s)` `.[ext]`
- `sitename`.`YY.MM.DD`.`actor(s)` `.[ext]`
- `SiteName` - `Actor(s)` `.[ext]`
- `sitename`.`actor(s)` `.[ext]`

Real world examples:
- `Blacked - 2018-12-11 - The Real Thing.mp4`
- `blacked.18.12.11.the.real.thing.mp4`
- `Blacked - Hot Vacation Adventures.mp4`
- `blacked.hot.vacation.adventures.mp4`
- `Blacked - 2018-09-07 - Alecia Fox.mp4`
- `blacked.18.09.07.alecia.fox.mp4`
- `Blacked - Alecia Fox Joss Lescaf.mp4`
- `blacked.alecia.fox.joss.lescaf.mp4`

Some sites do not have a search function available. This is where SceneID and Direct URL come in to play.
These usually don't make the most intuitive filenames, so it is often better to use the [Match...] function in Plex. See the [manual searching document](./manualsearch.md) for more information.

#### If You Would Prefer to Integrate SceneIDs into Your Filenames, Instead of Manually Matching in Plex, Here are Some Naming Structures We Recommend:

- `SiteName` - `YYYY-MM-DD` - `SceneID` `.[ext]`
- `sitename`.`YY.MM.DD`.`SceneID` `.[ext]`
- `SiteName` - `SceneID` `.[ext]`
- `sitename`.`SceneID` `.[ext]`
- `SiteName` - `SceneID` - `Scene Name` `.[ext]`
- `sitename`.`SceneID`.`scene.name` `.[ext]`

Real world examples:
- `EvilAngel - 2016-10-02 - 119883` (taken from the URL [https://www.evilangel.com/en/video/evilangel/Allie--Lilys-Slobbery-Anal-Threesome/**119883**](https://www.evilangel.com/en/video/evilangel/Allie--Lilys-Slobbery-Anal-Threesome/119883))
- `MomsTeachSex - 314082` (taken from the URL [https://momsteachsex.com/tube/watch/**314082**](https://momsteachsex.com/tube/watch/314082))
- `Babes - 3075191 - Give In to Desire` (taken from the URL [https://www.babes.com/scene/**3075191**/1](https://www.babes.com/scene/3075191/1))

> The filename parser lives in `phoenixadult/utils/processors/filename_parser.py`
> (`get_site_name_from_registry`). The site token is matched case-insensitively
> against the registry; the rest of the name resolves to a date, a SceneID, a
> title, and/or actor(s) depending on the site's `content_type`.
