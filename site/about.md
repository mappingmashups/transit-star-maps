# About Transit Star Maps

<p class="lede">City rail networks, drawn as if they were constellations in the night sky.</p>

## What am I looking at?

Each map is a city's subway or light rail network drawn as a constellation. Every star is a real station, placed where it really is, and the lines join stations that are next to each other on the network.

## What do the bigger and smaller stars mean?

Bigger stars mark the places where lines meet or branch, like transfer stations and junctions, plus a few line ends and landmark stations I wanted to stand out. On some maps there are also small, faint stars: in Boston, for example, those are the Green Line's street-running trolley stops, which are much closer together than the subway stations.

## Why straight lines?

The stars are in their real locations, but the lines between them are drawn straight, the way constellations are drawn on star charts, rather than following every curve of the track. It turns out that makes them look much more like constellations.

## Why did you pick these cities? Why didn't you do city X? Will you do my city next?

Not every city's subway network looks like a convincing constellation of stars in the sky.

- Some are too big, like London, Paris, or Tokyo. They have too many lines and stations. No real constellation has so many stars arranged in such tangled patterns.
- Some have too many straight lines, like New York and Chicago. Constellations should have organic, curvy arrangements of stars.
- Some networks are long and thin, stretched along a single corridor. Constellations sprawl in more than one direction.
- Meanwhile, other subway networks are too small, with only one or two lines. Those don't make for good constellations either.

The first Transit Star Map I made was of BART (Bay Area Rapid Transit) in the San Francisco Bay Area, and for me that's still the ideal balance: the right number of stations and lines, and the right organic curve to the lines. When picking new systems to add, I prefer the ones that are most like BART. (And yes, some of the systems I've already done, like Toronto or Los Angeles, don't quite fit my own rules.)

That said, if there's a system that fits these criteria and I haven't done it yet, maybe I just haven't gotten around to it. If you'd like to suggest a place I should add, please [open an issue on GitHub](https://github.com/mappingmashups/transit-star-maps/issues) or [get in touch](https://mappingmashups.net).

## Why are some of these systems that don't exist yet?

Two of the maps, Seattle and California, show networks that are still being planned or built: Link light rail at the full Sound Transit 3 build-out, and California High-Speed Rail with both of its phases. They show what those systems would look like when complete. Plans change, and these maps reflect the plans as of 2026.

## Are these AI generated?

When I created the first maps in this series back in 2015, AI coding tools weren't around yet. For this reboot of the site in 2026, as part of the [#30DayMapChallenge](https://30daymapchallenge.com/), I did use Claude Code to update the website and modernize the scripts that create these images. The scripts always use real data, so there are no made-up shapes or stations that don't exist. For the two planned systems, station locations are approximate, and some stations are one of several options still under consideration. All the design decisions are mine.

## How does it work?

The first version of these maps used a semi-automated process in TileMill, a map design tool that was a weird choice in retrospect, followed by a manual trip through Photoshop to make the transparent background needed for printing on shirts. None of that was worth building on.

The new process uses Python to download each transit agency's published data, clean it up so that each station is a single star and each pair of neighboring stations is joined by a single line, and draw the result as SVG and PNG images, including print-ready transparent versions. [All the code is on GitHub](https://github.com/mappingmashups/transit-star-maps).

## Haven't I seen something like this before?

Possibly! People have strong emotional attachments to their favorite transit networks, and there are probably many romanticized renderings of subway maps along these lines, although I haven't seen anything quite like these.

Some similar ideas I listed as inspiration when I started this project in 2015:

- [Line Posters](https://www.etsy.com/shop/LinePosters)
- [Transit Tees](https://www.transittees.com/)
- Neil Freeman's [Subway systems at the same scale](https://fakeisthenewreal.org/subway/) poster

## Are you really making money off this?

Hardly! I liked having one of these designs on a T-shirt, and I figured others might like the same thing. If you do too, [they're available on Zazzle](https://www.zazzle.com/transitstarmaps).

## Where does the data come from?

Every map is built from data the transit agencies publish themselves:

{{credits}}
