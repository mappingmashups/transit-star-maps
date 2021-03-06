@background: black;
//@background: transparent;
@starcolor: #ffa;

Map {
  background-color: @background;
}



.lines[TYPE='MAX'],
.lines[TYPE='MAX/SC'] {
  //line-width:2;
  line-width: 8;
  //line-color:lighten(@starcolor,10%);
  line-color: lightgray;
  line-cap: round;
}


.stations[TYPE='MAX'] {

  //second/marker-file: url("maki_icons/star-stroked-24.svg");
  //second/marker-width:12;
  
  // for the same icon
  second/marker-file: url("star_icon_3307/icon_3307_stroke.svg");
  second/marker-width:30;
  second/marker-fill:@background;
  
  /*
  // for just a circle
  second/marker-width:75;
  second/marker-transform:translate(1.5,1.5);
  */
  
  second/marker-fill:@background;
  second/marker-line-width: 35;
  second/marker-allow-overlap:true;

  first/marker-file: url("star_icon_3307/icon_3307.svg"); 
  first/marker-width:30;
  first/marker-fill:@starcolor;
  first/marker-allow-overlap:true;



}
