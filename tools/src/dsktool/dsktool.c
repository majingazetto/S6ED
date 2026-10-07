#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <ctype.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
// DLG Added -->
#include <time.h>
// DLG Added <--


#if defined (__WIN32__)
#include <malloc.h>
#include <dir.h>
#include <io.h>
#include <dos.h>
#else
#include <glob.h>
#endif

#include "msxboot.h"



#define LOG( s )	

#if (CPUBYTE)

#define BIGENDIAN(value) (((value&0x00FF)<<8)|((value&0xFF00)>>8))
#define BIGENDIANDINT(value) (  ((value & 0x000000FF) << 24) | ((value & 0x0000FF00) << 8) | ((value & 0x00FF0000)>>8) | ((value & 0xFF000000) >> 24) ) 

#else

#define BIGENDIAN(value) value
#define BIGENDIANDINT(value) value
#endif




typedef unsigned char byte;
typedef unsigned short word;
typedef struct tFileInfo
{
    char	strName[9];
    char	strExtension[4];
    int	iSize;
    int	iHour, iMinute, iSecond;
    int	iDay, iMonth, iYear;
    int	iFirst;
    int	iPosition;
    int	iAttributes;
} FILEINFO, *PFILEINFO;

byte *g_pDSKImage;
byte *g_pFat;
byte *g_pDirec;
byte *g_pCluster;

int g_iBytesPerSector;
int g_iClusterSize;
int g_iReservedSectors;
int g_iNumberOfFats;
int g_iDirectoryEntries;
int g_iSectorsPerDisk;
int iMediaID;
int g_iSectorsPerFat;
int g_iTracksPerSector;
int g_iDiskSides;
int g_iHiddenSectors;

int g_iFatElements;
int g_iAvaliableSectors;

// BS stands for BOOT SECTOR
#define BS_BYTES_PER_SECTOR			0
#define BS_CLUSTER_SIZE				BS_CLUSTER_SIZE			+ 1
#define BS_UNUSED_SECTORS			BS_BYTES_PER_SECTOR 	+ 1
#define BS_NUMBER_OF_FATS			BS_UNUSED_SECTORS		+ 1
#define BS_DIRECTORY_ENTRIES		BS_NUMBER_OF_FATS		+ 1
#define BS_SECTORS_PER_DISK			BS_DIRECTORY_ENTRIES	+ 1
#define BS_MEDIA_ID					BS_SECTORS_PER_DISK		+ 1
#define BS_SECTORS_PER_FAT			BS_MEDIA_ID				+ 1
#define BS_TRACKS_PER_SECTOR		BS_SECTORS_PER_FAT		+ 1
#define BS_DISK_SIDES				BS_TRACKS_PER_SECTOR	+ 1
#define BS_HIDDEN_SECTORS			BS_DISK_SIDES			+ 1

// Sizes of each field in bytes
#define BS_SIZE_BYTES_PER_SECTOR	2
#define BS_SIZE_CLUSTER_SIZE		1
#define BS_SIZE_UNUSED_SECTORS		1
#define BS_SIZE_NUMBER_OF_FATS		1
#define BS_SIZE_DIRECTORY_ENTRIES	1
#define BS_SIZE_SECTORS_PER_DISK	2
#define BS_SIZE_MEDIA_ID			1
#define BS_SIZE_SECTORS_PER_FAT		2
#define BS_SIZE_TRACKS_PER_SECTOR	0x18
#define BS_SIZE_DISK_SIDES			2
#define BS_SIZE_HIDDEN_SECTORS		2

#define BS_OFFSET_BYTES_PER_SECTOR	0x0B	// 2 bytes	(In bytes)
#define BS_OFFSET_CLUSTER_SIZE		0x0D	// 1 byte	(In sectors)
#define BS_OFFSET_UNUSED_SECTORS	0x0E	// 1 byte	(Unused by MSX-DOS)
#define BS_OFFSET_NUMBER_OF_FATS	0x10	// 1 byte
#define BS_OFFSET_DIRECTORY_ENTRIES	0x11	// 2 bytes	(How many files can be created)
#define BS_OFFSET_SECTORS_PER_DISK	0x13	// 2 bytes
#define BS_OFFSET_MEDIA_ID			0x15
#define BS_OFFSET_SECTORS_PER_FAT	0x16	// 2 bytes
#define BS_OFFSET_TRACKS_PER_SECTOR	0x18
#define BS_OFFSET_DISK_SIDES		0x1A	// 2 bytes	(One or two sides)
#define BS_OFFSET_HIDDEN_SECTORS	0x1C	// 2 bytes

#define WORDAT( array, position ) *(word*)( array + position )
#define BYTEAT( array, position ) *(byte*)( array + position )



char **__crt0_glob_function (char *_argument)
{
    return NULL;  
}

void ExtractWPath (char *pName, char *pNoPath) {

    int i=0;
    // Encontrar el final
    while ( pName[i] != 0)
        i++;



    // Buscar el "/"



    while ( (i>=0) && (( pName[i] != '/')  && (pName[i] != 0x5C)))
        i--;

    i++;
    // Copiar el nombre
    while ( pName[i] != 0)
    {
        *pNoPath++ = pName[i];
        i++;
    }
    *pNoPath++ = 0;

}     


void LoadDSK( char *strDSKName, int error )
{
    FILE* pFile;

    LOG( strDSKName );

    g_pDSKImage = (byte*)malloc(720*1024*sizeof(byte));
    pFile = fopen( strDSKName, "rb" );
    if( pFile == NULL )
    {
        LOG( "File not exist" );
        if( error )
        {
            printf( "Error in .DSK file\n" );
            exit( 2 );
        }
        LOG( "Resseting data" );
        memset( g_pDSKImage, 0, 720*1024 );
        memcpy( g_pDSKImage, msxboot, 512 );
    }
    else
    {
        int sizeRead; 
        sizeRead = fread( g_pDSKImage, sizeof(byte), 720*1024, pFile );
        fclose( pFile );
    }

    g_iBytesPerSector		= BIGENDIAN (WORDAT( g_pDSKImage, BS_OFFSET_BYTES_PER_SECTOR	));
    g_iReservedSectors		= BIGENDIAN (WORDAT( g_pDSKImage, BS_OFFSET_UNUSED_SECTORS		));
    g_iNumberOfFats			= BYTEAT( g_pDSKImage, BS_OFFSET_NUMBER_OF_FATS		);
    g_iDirectoryEntries		= BIGENDIAN (WORDAT( g_pDSKImage, BS_OFFSET_DIRECTORY_ENTRIES	));
    g_iSectorsPerFat		= BIGENDIAN (WORDAT( g_pDSKImage, BS_OFFSET_SECTORS_PER_FAT	));


    g_pFat					= g_pDSKImage + g_iBytesPerSector*g_iReservedSectors;
    g_pDirec				= g_pFat + g_iBytesPerSector*( g_iSectorsPerFat*g_iNumberOfFats );
    g_pCluster				= g_pDirec + g_iDirectoryEntries*32;
    g_iAvaliableSectors		= 80*9*2 - g_iReservedSectors - g_iSectorsPerFat*g_iNumberOfFats;
    g_iAvaliableSectors		-= g_iDirectoryEntries*32/g_iBytesPerSector;
    g_iFatElements			= g_iAvaliableSectors/2;
    if( pFile == NULL )
    {
        g_pFat[0] = 0xF9;
        g_pFat[1] = 0xFF;
        g_pFat[2] = 0xFF;
    }
    LOG( "LoadDSK ends" );
}

int NextLink( int iLink )
{
    int iPosition;

    iPosition = ( iLink >> 1 )*3;
    if( iLink & 1 )	// Multiple of two?
    {
        return ( ( (int)( g_pFat[iPosition + 2]) ) << 4 ) + ( g_pFat[iPosition + 1] >> 4 );
    }
    else 
    {
        return ( ( (int)( g_pFat[iPosition + 1] &0xF ) ) << 8 ) + g_pFat[iPosition];
    }
}

int RemoveLink( int iLink )
{
    int iPosition;
    int iCurrent;

    iPosition = ( iLink >> 1 )*3;
    if( iLink & 1 )	// Multiple of two?
    {
        iCurrent=( ( (int)( g_pFat[iPosition+2] ) ) << 4 )+(g_pFat[iPosition + 1] >> 4 );
        g_pFat[iPosition + 2] = 0;
        g_pFat[iPosition + 1] &= 0xF;
        return iCurrent;
    }
    else
    {
        iCurrent=( ( (int)( g_pFat[iPosition+1] & 0xF ) ) << 8 ) + g_pFat[iPosition];
        g_pFat[iPosition] = 0;
        g_pFat[iPosition + 1] &= 0xF0;
        return iCurrent;
    }
}

void StoreFat( int iLink, int iNext )
{
    int iPosition;

    iPosition = ( iLink >> 1 )*3;
    if( iLink & 1 )	// Multiple of two?
    {
        g_pFat[iPosition + 2] = iNext >> 4;
        g_pFat[iPosition + 1] &= 0xF;
        g_pFat[iPosition + 1] |= ( iNext & 0xF ) << 4;
    }
    else
    {
        g_pFat[iPosition]		= iNext & 0xFF;
        g_pFat[iPosition + 1]	&= 0xF0;
        g_pFat[iPosition + 1]	|= iNext >> 8;
    }
}

PFILEINFO GetFileInfo( int iPosition )
{
    PFILEINFO pFileInfo;
    byte *pDir;
    int iIndexCharacter;
    int iIndexData;
    pDir = g_pDirec + iPosition*32;
    if( *pDir < 0x20 || *pDir >= 0x80 ) {


        return NULL;

    }		
    pFileInfo = (PFILEINFO)malloc( sizeof(FILEINFO) );
    for( iIndexCharacter = 0; iIndexCharacter < 8; iIndexCharacter++ )
    {
        pFileInfo->strName[iIndexCharacter] = ( pDir[iIndexCharacter] == 0x20 )?0:pDir[iIndexCharacter];
    }
    pFileInfo->strName[8] = 0;

    for( iIndexCharacter = 0; iIndexCharacter < 3; iIndexCharacter++ )
    {
        pFileInfo->strExtension[iIndexCharacter] = ( pDir[iIndexCharacter + 8] == 0x20 )?0:pDir[iIndexCharacter + 8];
    }
    pFileInfo->strExtension[3] = 0;

    pFileInfo->iSize	= BIGENDIANDINT( *(int *) (pDir+0x1C) );

    iIndexData				= BIGENDIAN (*(word*)( pDir + 0x16 ));
    pFileInfo->iSecond		= ( iIndexData & 0x1F ) << 1;
    pFileInfo->iMinute		= ( iIndexData >> 5 ) & 0x3F;
    pFileInfo->iHour		= iIndexData >> 11;

    iIndexData				= BIGENDIAN (*(word*)( pDir + 0x18 ));
    pFileInfo->iDay			= iIndexData & 0x1F;
    pFileInfo->iMonth		= ( iIndexData >> 5 ) & 0xF;
    pFileInfo->iYear		= 1980 + ( iIndexData >> 9 );

    pFileInfo->iFirst		= BIGENDIAN (*(word*)(pDir+0x1A));
    pFileInfo->iPosition	= iPosition;
    pFileInfo->iAttributes	= *( pDir + 0xB );

    return pFileInfo;
}

int BytesFree( void )
{
    int iIndexFatElement, iAvailable = 0;

    for( iIndexFatElement = 2; iIndexFatElement < 2 + g_iFatElements; iIndexFatElement++ )
    {
        if( !NextLink( iIndexFatElement ) ) iAvailable++;
    }
    return iAvailable*1024;
}

void ListDSK( void )
{
    int i;
    PFILEINFO pFileInfo;
    char strName[20], strDate[30], strTime[30], strSize[30];

    for( i=0; i<8; i++ )
    {
        strName[i] = g_pDSKImage[3 + i];
    }
    strName[8] = 0;
    printf( "Name of volume: %s\n\n", strName );
    for( i=0; i<g_iDirectoryEntries; i++ )
    {
        pFileInfo = GetFileInfo( i );
        if( pFileInfo!=NULL )
        {
            if( pFileInfo->strExtension[0] )
            {
                sprintf( strName,"%s.%s", pFileInfo->strName, pFileInfo->strExtension );
            }

            else
            {
                strcpy( strName, pFileInfo->strName );
            }
            sprintf( strSize,"%7d", pFileInfo->iSize );
            if( pFileInfo->iAttributes & 0x8 ) strcpy( strSize,"  <VOL>" );
            if( pFileInfo->iAttributes & 0x10) strcpy( strSize,"  <DIR>" );
            sprintf( strDate, "%d/%02d/%d", pFileInfo->iDay, pFileInfo->iMonth, pFileInfo->iYear );
            sprintf( strTime, "%d:%02d:%02d", pFileInfo->iHour, pFileInfo->iMinute, pFileInfo->iSecond );
            printf( "%-13s %s %10s %8s\n", strName, strSize, strDate, strTime );

        }
        free( pFileInfo );


    }
    printf( "\n%d bytes free\n", BytesFree() );
}

int Match( PFILEINFO pFileInfo, char *strName )
{
    // Matches wildcard?
    char *p=pFileInfo->strName;
    int iStatus = 0, iIndexChar;

    for( iIndexChar = 0; iIndexChar < 8; iIndexChar++ )
    {
        if( !*strName )
            break;
        if (*strName == '*' )
        {
            iStatus=1;
            strName++;
            break;
        }
        if( *strName == '.' )
            break;
        if( toupper( *strName++ ) != toupper( *p++ ) )
            return 0;
    }
    if( !iStatus && ( iIndexChar < 8 ) && ( *p != 0 ) ) 
        return 0;
    p=pFileInfo->strExtension;
    if( !*strName && !*p ) return 1;
    if( *strName++ != '.' ) return 0;
    for( iIndexChar = 0; iIndexChar < 3; iIndexChar++ )
    {
        if( *strName == '*' )
            return 1;
        if( toupper( *strName++ ) != toupper( *p++ ) )
            return 0;
    }
    return 1;
}

void ParseTree( char *strName, void (*Action)(PFILEINFO) )
{
    int i;
    PFILEINFO pFileInfo;

    for( i=0; i<g_iDirectoryEntries; i++ )
    {
        if( ( pFileInfo = GetFileInfo( i ) ) != NULL )
        {
            if( Match( pFileInfo, strName ) )
            {
                Action( pFileInfo );
            }
            free( pFileInfo );
        }
    }
}

void ParseDSK( int iArgCount, char **pstrArgVector, void (*Action)(PFILEINFO) )
{
    int iIndexArg;

    if( iArgCount == 3 )
    {
        ParseTree( "*.*", Action );
    }
    else
    {
        for( iIndexArg = 3; iIndexArg < iArgCount; iIndexArg++ )
            ParseTree( pstrArgVector[iIndexArg], Action );
    }
}

void Extract( PFILEINFO pFileInfo )
{
    byte *pBuffer,*p;
    FILE* pFile;
    char strFileName[20];
    int iCurrent;

    sprintf( strFileName,"%s.%s", pFileInfo->strName, pFileInfo->strExtension );
    printf( "extracting %s\n", strFileName );
    pBuffer = (byte*)malloc( ( pFileInfo->iSize + 1023 ) & ( ~1023 ) );
    memset( pBuffer, 0x1a, pFileInfo->iSize );

    pFile = fopen( strFileName, "wb" );
    iCurrent = pFileInfo->iFirst;
    p = pBuffer;
    do
    {
        memcpy( p, g_pCluster + ( iCurrent - 2 )*1024, 1024 );
        p += 1024;
        iCurrent = NextLink( iCurrent );
    } while( iCurrent != 0xFFF );
    fwrite( pBuffer, sizeof(byte), pFileInfo->iSize, pFile );
    fclose( pFile );
    free( pBuffer );
}

void Wipe( PFILEINFO pFileInfo )
{
    int iCurrent;

    iCurrent = pFileInfo->iFirst;
    do
    {
        iCurrent = RemoveLink( iCurrent );
    } while( iCurrent != 0xFFF );
    g_pDirec[pFileInfo->iPosition*32] = 0xE5;
}

void Delete( PFILEINFO pFileInfo )
{
    printf( "deleting %s.%s\n", pFileInfo->strName, pFileInfo->strExtension );
    Wipe( pFileInfo );
}

void FlushDSK( char *strDSKName )
{
    FILE *pFile;

    memcpy( g_pFat + g_iBytesPerSector*g_iSectorsPerFat, g_pFat, g_iBytesPerSector*g_iSectorsPerFat );
    pFile = fopen( strDSKName, "wb" );
    fwrite( g_pDSKImage, sizeof(byte), 720*1024, pFile );
    fclose( pFile );
}

int GetFree( void )
{
    int i;

    for( i = 2; i < ( 2 + g_iFatElements ); i++ )
    {
        if( !NextLink( i ) ) return i;
    }
    printf ("Internal error\n");
    exit (5);
}

int GetNextFree(void)
{
    int i, iStatus = 0;

    for( i = 2; i < ( 2 + g_iFatElements ); i++ )
    {
        if( !NextLink( i ) ) 
        {
            if( iStatus ) 
                return i;
            else
                iStatus = 1;
        }
    }
    printf ("Internal error\n");
    exit (5);
}

long FileLength( FILE* pFile )
{
    long lLength;

    long lCurrentPosition = ftell( pFile );
    fseek( pFile, 0L, SEEK_END );
    lLength = ftell( pFile );
    fseek( pFile, lCurrentPosition, SEEK_SET );

    return lLength;
}

void AddSingleFile( char *strFileNameInt, char *strFilePathName )
{
    int i, iTotal;
    int bFound = 0;
    PFILEINFO pFileInfo;
    FILE *pFile;
    byte *pBuffer;
    int iSize;

    struct tm * pFullTime;

    int iFirst;
    int iCurrent;
    int iNext;
    int iPosition;
    char *p;
    char strFullName[250];
    char strFileName[250];

#if defined (__WIN32__)
    strcpy( strFullName, strFilePathName );
    strcat( strFullName,strFileNameInt );
    strcpy( strFileName,strFileNameInt);
#else

    strcpy( strFullName,strFileNameInt );		
    ExtractWPath (strFileNameInt,strFileName);
#endif


    pFile = fopen( strFullName, "rb" );

    for( i=0; i < g_iDirectoryEntries; i++ )
    {
        if( ( pFileInfo = GetFileInfo( i ) ) != NULL )
        {
            if( Match( pFileInfo, strFileName ) )
            {
                bFound = 1;
                Wipe( pFileInfo );
            }
            free( pFileInfo );
        }
    }

    if( ( iSize = FileLength( pFile ) ) > BytesFree() )
    {
        printf ( "disk full\n" );
        exit( 4 );
    }

    if( bFound )    
        printf( "updating %s\n", strFileName );
    else
        printf( "  adding %s\n", strFileName );

    for( i = 0; i < g_iDirectoryEntries; i++ )
    {
        if( g_pDirec[i*32] < 0x20 || g_pDirec[i*32] >= 0x80 )
            break;
        if( i == g_iDirectoryEntries )
        {
            printf( "directory full\n" );
            exit( 6 );
        }
    }
    iPosition = i;

    pBuffer = (byte*)malloc( sizeof(byte)*( ( iSize + 1023 ) & ( ~1023 ) ) );
    int sizeRead; 
    sizeRead = fread( pBuffer, sizeof(byte), iSize, pFile );


    fclose( pFile );

    iTotal = ( iSize + 1023 ) >> 10;
    iCurrent = iFirst = GetFree();

    for( i=0; i < iTotal; )
    {
        memcpy( g_pCluster + ( iCurrent - 2 )*1024, pBuffer, 1024 );
        pBuffer += 1024;
        if( ++i == iTotal )
            iNext = 0xFFF;
        else
            iNext = GetNextFree();
        StoreFat( iCurrent, iNext );
        iCurrent = iNext;
    }

    memset( g_pDirec + iPosition*32, 0, 32 );
    memset( g_pDirec + iPosition*32, 0x20, 11 );
    i=0; 
    for( p = strFileName; *p ; p++ )
    {
        if( *p == '.' )
        {
            i = 8;
            continue;
        }
        g_pDirec[iPosition*32 + i++] = toupper( *p );
    }


    *(word*)( g_pDirec + iPosition*32 + 0x1A ) = BIGENDIAN (iFirst);
    *(int*)( g_pDirec + iPosition*32 + 0x1C ) = BIGENDIANDINT(iSize);

    const time_t CurrentTime = time(NULL);
    pFullTime =  localtime( &CurrentTime );


    int value;



    value = (int)  ( ( pFullTime->tm_sec >> 1 ) + ( pFullTime->tm_min << 5 ) + (
                pFullTime->tm_hour << 11 ));

    *(word*)( g_pDirec + iPosition*32 + 0x16 ) =  BIGENDIAN( value); 

    value = (int) (( pFullTime->tm_mday ) + ( ((pFullTime->tm_mon)+1) << 5 ) + (
                (( pFullTime->tm_year)-80) << 9) );
    *(word*)( g_pDirec + iPosition*32+0x18 ) = BIGENDIAN( value );


#if defined (__WIN32__)
    free( pBuffer );
#endif


}



#if defined (__WIN32__)
void AddFiles( char *strFileName )
{
    LOG( strFileName );
    struct _finddata_t FindData;  
    int status;
    char *temp1,*temp2;
    char strDirectory[200];

    status = _findfirst( strFileName, &FindData );
    temp1 = NULL;
    temp2 = strFileName;
    // Change slash by backslash
    int iIndexChar = 0;
    while( strFileName[iIndexChar] != '\0' )
    {
        if( strFileName[iIndexChar] == '/' )
        {
            strFileName[iIndexChar] = '\\';
        }
        iIndexChar++;
    }
    // Get Directory path if specified	
    while( ( temp2 = strstr( temp2, "\\" ) ) != NULL )
    {
        temp1 = temp2;
        temp2++;
    }
    if( temp1 != NULL )
    {
        memset( strDirectory, 0, 200 );
        memcpy( strDirectory, strFileName, temp1 - strFileName );
        strcat( strDirectory, "\\" );
    }
    else
    {
        *strDirectory = 0;
    }
    while( status >= 0 )
    {  
        AddSingleFile( FindData.name, strDirectory );
        status = _findnext( status, &FindData );
    }
    _findclose( status );
}
#else

void AddFiles( char *strFileName )
{
    LOG( strFileName );


    glob_t	g = {0, 0, 0, 0, 0, 0, 0, 0, 0};

    int i=0;
    char *temp1,*temp2;
    char strDirectory[200];

    //status = findfirst( strFileName, &FindData );

    /* Call glob to expand it. */
    glob(strFileName,GLOB_NOSORT | GLOB_TILDE  ,NULL,&g);


    temp1 = NULL;
    temp2 = strFileName;


    // Get Directory path if specified	
    while( ( temp2 = strstr( temp2, "/" ) ) != NULL )
    {
        temp1 = temp2;
        temp2++;
    }
    if( temp1 != NULL )
    {
        memset( strDirectory, 0, 200 );
        memcpy( strDirectory, strFileName, temp1 - strFileName );
        strcat( strDirectory, "/" );
    }
    else
    {
        *strDirectory = 0;
    }


    if (g.gl_pathc > 0) {


        for (i=0; i<g.gl_pathc; ++i) {
            AddSingleFile( g.gl_pathv[i], strDirectory );
        }


    }				


    globfree(&g);


}
#endif // defined __WIN32__

void AddToDSK( int argc, char **argv )
{
    int i;

    for( i = 3; i<argc; i++ )
    {
        LOG( "AddToDSK" );
        AddFiles( argv[i] );
    }
}





int main( int argc, char **argv )
{
    printf( "DSK Tool v1.1\n" );
    printf( "Copyright (C) 1998 by Ricardo Bittencourt\n" );
    printf( "This file is under GNU GPL, read COPYING for details\n\n" );
    printf( "Modified version by David Lucena in 2006\n\n" );
    printf( "Generic version by Armando Perez (Ramones) 2006 \n\n" ) ;

    if( argc<3 )
    {
        printf ( "Usage: DSKTOOL command archive [files]\n\n" );
        printf ( "commands:\n" );
        printf ( "\t\tL\tlist contents of .DSK\n" );
        printf ( "\t\tE\textract files from .DSK\n" );
        printf ( "\t\tA\tadd files to .DSK\n" );
        printf ( "\t\tD\tdelete files from .DSK\n" );
        printf ( "\nexamples:\n" );
        printf ( "\t\tDSKTOOL L TALKING.DSK\n" );
        printf ( "\t\tDSKTOOL E TALKING.DSK FUZZ*.*\n" );
        printf ( "\t\tDSKTOOL A TALKING.DSK MSXDOS.SYS COMMAND.COM\n" );
        printf ( "\t\tDSKTOOL D TALKING.DSK *.BAS *.BIN\n" );
        exit (1);
    }
    switch( toupper( argv[1][0] ) )
    {
        case 'L':
            {
                LoadDSK( argv[2], 1 );
                ListDSK();
                break;
            }
        case 'E':
            {
                LoadDSK( argv[2], 1 );
                ParseDSK( argc, argv, Extract );
                break;
            }
        case 'D':
            {
                LoadDSK( argv[2], 1 );
                ParseDSK( argc, argv, Delete );
                FlushDSK( argv[2] );
                break;
            }
        case 'A':
            {
                LoadDSK( argv[2], 0 );
                AddToDSK( argc, argv );
                FlushDSK( argv[2] );
                break;
            }
        default:
            {
                printf( "Command not supported\n" );
                exit( 3 );
            }
    }
    return 0;
}
