transit-star-maps
=================

transit maps that look like constellations because trains + stars = &lt;3

What makes a good transit star chart?
-------------------------------------
 * The transit system needs to be complicated enough to be interesting. Sorry, [one-line systems](http://en.wikipedia.org/wiki/Link_Light_Rail) are boring.
 * Not too complicated! Sorry, [hundreds of stations and dozens of lines](http://en.wikipedia.org/wiki/New_York_City_Subway) is more complicated than any constellation. It wouldn't look right.
 * Ideally some hierarchy of stations so we can use different sizes of stars. Maybe express vs local stops, or transfer stations could be larger stars, etc.

![BART map](outputs/bart_v0.1.png)

Workflow:
---------

The stylesheet is designed with BART in mind.

Use tilemill's export panel. Export at target zoom of 13, and pixel width of the image of 3000px.

Using Zazzle, we upload a t-shirt image that roughly fills the printable area of a shirt, maybe 8 to 10 inches wide. So 3000px at 300 dpi makes sense.

The first test shirt ended up with stars that were about 1/8" of an inch wide. This is unsatisfying. For the next round, I'm trying 1/4" stars. At 300 dpi, this means the stars should be about 75 pixels wide.

Then, the image needs to be loaded into photoshop (or similar) to remove the background. For t-shirt printing the background needs to be transparent. But, we can't just generate a transparent image from tilemill, because we need the stars to have a black outline that cuts out the underlying paths.


